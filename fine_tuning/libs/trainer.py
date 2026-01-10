"""
训练器 - LoRA/QLoRA 微调主逻辑
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType
)

from .data_loader import prepare_dataset, get_data_collator

logger = logging.getLogger(__name__)


def load_config(config_path: str | Path) -> Dict:
    """加载训练配置"""
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 解析相对路径为绝对路径
    base_dir = config_path.parent.parent  # fine_tuning目录
    
    # 转换路径
    for key in ['base_model', 'train_data', 'val_data', 'test_data']:
        if key in config and config[key]:
            path = Path(config[key])
            if not path.is_absolute():
                config[key] = str((base_dir / path).resolve())
    
    # 确保输出目录存在
    output_dir = Path(config['output_dir'])
    if not output_dir.is_absolute():
        config['output_dir'] = str((base_dir / output_dir).resolve())
    
    # 创建输出目录
    Path(config['output_dir']).mkdir(parents=True, exist_ok=True)
    
    return config


def setup_model_and_tokenizer(config: Dict):
    """
    加载模型和 tokenizer
    
    支持：
    - 标准 LoRA
    - QLoRA（4bit/8bit 量化）
    """
    import os
    model_name_or_path = config["base_model"]
    logger.info(f"Loading model from: {model_name_or_path}")
    
    # 检查是否为本地路径 (多重检查确保正确检测)
    # 1. 检查是否存在为目录
    # 2. 检查路径是否包含路径分隔符 (表示是路径而非 HF repo id)
    is_local = os.path.isdir(model_name_or_path) or os.path.exists(model_name_or_path)
    # 如果路径包含驱动器号(Windows)或以/开头(Unix)，也视为本地路径
    if not is_local:
        is_local = (os.sep in model_name_or_path or 
                    model_name_or_path.startswith('/') or 
                    (len(model_name_or_path) > 2 and model_name_or_path[1] == ':'))
    logger.info(f"Is local model: {is_local}, path exists: {os.path.exists(model_name_or_path)}")
    
    # 加载 tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_name_or_path,
        trust_remote_code=config.get("trust_remote_code", True),
        use_fast=True,
        local_files_only=is_local
    )
    
    # 确保有 pad_token
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    

    
    # 配置量化（如果使用 QLoRA）
    quantization_config = None
    if config.get("use_qlora", False) or config.get("load_in_4bit", False):
        logger.info("Setting up QLoRA (4bit quantization)...")
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=getattr(torch, config.get("bnb_4bit_compute_dtype", "bfloat16")),
            bnb_4bit_quant_type=config.get("bnb_4bit_quant_type", "nf4"),
            bnb_4bit_use_double_quant=config.get("bnb_4bit_use_double_quant", True)
        )
    elif config.get("load_in_8bit", False):
        logger.info("Setting up 8bit quantization...")
        quantization_config = BitsAndBytesConfig(load_in_8bit=True)
    
    # 加载模型
    model = AutoModelForCausalLM.from_pretrained(
        model_name_or_path,
        quantization_config=quantization_config,
        trust_remote_code=config.get("trust_remote_code", True),
        dtype=torch.bfloat16 if config.get("bf16", True) else torch.float16,
        device_map="auto",  # 自动分配设备
        local_files_only=is_local
    )
    
    # 如果使用量化，准备模型
    if quantization_config is not None:
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=config.get("gradient_checkpointing", True)
        )
    
    # 同步 model config
    model.config.pad_token_id = tokenizer.pad_token_id
    if tokenizer.bos_token_id is not None:
        model.config.bos_token_id = tokenizer.bos_token_id
    if hasattr(model, "generation_config") and model.generation_config:
        model.generation_config.pad_token_id = tokenizer.pad_token_id
        if tokenizer.bos_token_id is not None:
            model.generation_config.bos_token_id = tokenizer.bos_token_id
    
    # 配置 LoRA
    if config.get("use_lora", True):
        logger.info("Setting up LoRA...")
        lora_config = LoraConfig(
            r=config.get("lora_r", 8),
            lora_alpha=config.get("lora_alpha", 16),
            lora_dropout=config.get("lora_dropout", 0.05),
            target_modules=config.get("lora_target_modules"),
            bias="none",
            task_type=TaskType.CAUSAL_LM
        )
        
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()
    
    return model, tokenizer


def setup_training_arguments(config: Dict) -> TrainingArguments:
    """配置训练参数"""
    
    # 创建输出目录
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    
    training_args = TrainingArguments(
        # 基础配置
        output_dir=str(output_dir),
        overwrite_output_dir=True,
        
        # 训练超参
        num_train_epochs=config.get("num_train_epochs", 3),
        per_device_train_batch_size=config.get("per_device_train_batch_size", 1),
        per_device_eval_batch_size=config.get("per_device_eval_batch_size", 1),
        gradient_accumulation_steps=config.get("gradient_accumulation_steps", 8),
        
        # 学习率
        learning_rate=config.get("learning_rate", 1e-4),
        lr_scheduler_type=config.get("lr_scheduler_type", "cosine"),
        warmup_ratio=config.get("warmup_ratio", 0.1),
        
        # 优化器
        optim=config.get("optim", "adamw_torch"),
        weight_decay=config.get("weight_decay", 0.01),
        adam_beta1=config.get("adam_beta1", 0.9),
        adam_beta2=config.get("adam_beta2", 0.999),
        max_grad_norm=config.get("max_grad_norm", 1.0),
        
        # 保存策略
        save_strategy=config.get("save_strategy", "steps"),
        save_steps=config.get("save_steps", 100),
        save_total_limit=config.get("save_total_limit", 3),
        
        # 评估策略
        eval_strategy=config.get("eval_strategy", "steps"),
        eval_steps=config.get("eval_steps", 50),
        eval_accumulation_steps=config.get("eval_accumulation_steps", 4),
        
        # 日志
        logging_dir=str(output_dir / "logs"),
        logging_steps=config.get("logging_steps", 10),
        logging_first_step=config.get("logging_first_step", True),
        
        # 混合精度
        bf16=config.get("bf16", True),
        fp16=config.get("fp16", False),
        
        # 梯度检查点
        gradient_checkpointing=config.get("gradient_checkpointing", True),
        gradient_checkpointing_kwargs=config.get("gradient_checkpointing_kwargs", {"use_reentrant": False}),
        
        # 数据加载
        dataloader_num_workers=config.get("dataloader_num_workers", 4),
        dataloader_pin_memory=config.get("dataloader_pin_memory", True) and torch.cuda.is_available(),
        
        # 其他
        seed=config.get("seed", 42),
        report_to=config.get("report_to", ["tensorboard"]),
        
        # 加载最佳模型
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
    )
    
    return training_args


def train(config_path: str | Path):
    """
    主训练函数
    
    Args:
        config_path: 训练配置文件路径
    """
    # 加载配置
    config = load_config(config_path)
    logger.info(f"Loaded config from {config_path}")
    
    # 输出目录（已在load_config中创建）
    output_dir = Path(config["output_dir"])
    logger.info(f"Output directory: {output_dir}")
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(output_dir / "training.log"),
            logging.StreamHandler()
        ]
    )
    
    # 加载模型和 tokenizer
    model, tokenizer = setup_model_and_tokenizer(config)
    
    # 准备数据集
    logger.info("Preparing datasets...")
    tokenized_datasets = prepare_dataset(config, tokenizer)
    
    # 数据整理器
    data_collator = get_data_collator(
        tokenizer=tokenizer,
        max_length=config.get("max_seq_length", 4096),
        train_on_inputs=config.get("train_on_inputs", False)
    )
    
    # 训练参数
    training_args = setup_training_arguments(config)
    
    # 创建 Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_datasets["train"],
        eval_dataset=tokenized_datasets.get("validation"),
        processing_class=tokenizer,
        data_collator=data_collator,
    )
    
    # 开始训练
    logger.info("Starting training...")
    train_result = trainer.train()
    
    # 保存最终模型
    logger.info("Saving final model...")
    trainer.save_model()
    
    # 保存训练指标
    metrics = train_result.metrics
    trainer.log_metrics("train", metrics)
    trainer.save_metrics("train", metrics)
    trainer.save_state()
    
    logger.info("Training completed!")
    logger.info(f"Model saved to: {config['output_dir']}")

