"""
数据加载器 - 加载和处理 SFT 数据

从 data/final/*_sft.jsonl 加载数据，转换为 HF Datasets 格式，应用 chat template
"""
import json
from pathlib import Path
from typing import Optional, Dict, List
from datasets import Dataset, DatasetDict
import logging

logger = logging.getLogger(__name__)


def load_sft_jsonl(file_path: str | Path) -> List[Dict]:
    """加载 SFT JSONL 文件"""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Data file not found: {file_path}")
    
    samples = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                samples.append(sample)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON at line {line_num}: {e}")
                continue
    
    logger.info(f"Loaded {len(samples)} samples from {file_path}")
    return samples


def format_chat_sample(sample: Dict, tokenizer) -> Dict:
    """
    将 SFT 样本格式化为训练格式
    
    输入格式：
    {
        "messages": [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ],
        "metadata": {...}
    }
    
    输出格式：
    {
        "input_ids": [...],
        "labels": [...],  # system/user 部分为 -100（不计算 loss）
        "attention_mask": [...]
    }
    """
    messages = sample.get("messages", [])
    if not messages:
        raise ValueError("Sample has no messages")
    
    # 使用 tokenizer 的 apply_chat_template
    # 注意：不同模型的 chat template 可能不同
    try:
        # 尝试使用 tokenizer 的 chat template
        formatted_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False
        )
    except Exception as e:
        logger.warning(f"Failed to apply chat template: {e}, using fallback")
        # Fallback：简单拼接
        formatted_text = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            formatted_text += f"<|im_start|>{role}\n{content}<|im_end|>\n"
    
    return {
        "text": formatted_text,
        "messages": messages,
        "metadata": sample.get("metadata", {})
    }


def create_train_dataset(
    train_path: str | Path,
    val_path: Optional[str | Path] = None,
    tokenizer = None,
    max_samples: Optional[int] = None
) -> DatasetDict:
    """
    创建训练数据集
    
    Args:
        train_path: 训练数据路径
        val_path: 验证数据路径（可选）
        tokenizer: tokenizer 实例
        max_samples: 最大样本数（用于快速测试）
    
    Returns:
        DatasetDict 包含 train 和可选的 validation split
    """
    # 加载训练数据
    train_samples = load_sft_jsonl(train_path)
    if max_samples:
        train_samples = train_samples[:max_samples]
        logger.info(f"Limited training samples to {max_samples}")
    
    # 格式化样本
    formatted_train = [format_chat_sample(s, tokenizer) for s in train_samples]
    train_dataset = Dataset.from_list(formatted_train)
    
    datasets = {"train": train_dataset}
    
    # 加载验证数据（如果提供）
    if val_path:
        val_samples = load_sft_jsonl(val_path)
        if max_samples:
            val_samples = val_samples[:max_samples // 5]  # 验证集取 1/5
        formatted_val = [format_chat_sample(s, tokenizer) for s in val_samples]
        datasets["validation"] = Dataset.from_list(formatted_val)
    
    return DatasetDict(datasets)


def get_data_collator(tokenizer, max_length: int = 4096, train_on_inputs: bool = False):
    """
    获取数据整理器（Data Collator）
    
    Args:
        tokenizer: tokenizer 实例
        max_length: 最大序列长度
        train_on_inputs: 是否在 system/user 部分计算 loss
    
    Returns:
        DataCollatorForSeq2Seq 实例
    """
    from transformers import DataCollatorForSeq2Seq
    
    # 标准的 Seq2Seq data collator
    # 会自动处理 padding、attention_mask 和 labels
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=None,  # 如果不需要动态 padding 可以不传
        padding="longest",  # 动态 padding 到 batch 中最长序列
        max_length=max_length,
        label_pad_token_id=-100  # 标准做法：padding 位置的 label 为 -100
    )
    
    return data_collator


def tokenize_function(examples: Dict, tokenizer, max_length: int = 4096, train_on_inputs: bool = False):
    """
    Tokenization 函数（用于 dataset.map）
    
    处理 chat template 并生成 input_ids、attention_mask 和 labels
    """
    texts = examples["text"]
    
    # Tokenize
    tokenized = tokenizer(
        texts,
        truncation=True,
        max_length=max_length,
        padding=False,  # 不在这里 padding，留给 data collator
        return_tensors=None
    )
    
    # 创建 labels
    # 如果 train_on_inputs=False，需要 mask 掉 system/user 部分
    if not train_on_inputs:
        labels = []
        for i, input_ids in enumerate(tokenized["input_ids"]):
            # 简化实现：直接复制 input_ids 作为 labels
            # 更精细的实现需要找到 assistant 回复的起始位置
            # 这里假设使用 apply_chat_template 时已经处理好格式
            label = input_ids.copy()
            
            # TODO: 根据 chat template 找到 assistant 部分的起始位置
            # 将 system/user 部分设置为 -100
            # 这需要根据具体的 tokenizer 和 chat template 实现
            
            labels.append(label)
        
        tokenized["labels"] = labels
    else:
        # 如果训练整个序列，labels 就是 input_ids
        tokenized["labels"] = tokenized["input_ids"].copy()
    
    return tokenized


def prepare_dataset(
    config: Dict,
    tokenizer
):
    """
    准备完整的训练数据集
    
    Args:
        config: 训练配置字典
        tokenizer: tokenizer 实例
    
    Returns:
        处理好的 DatasetDict
    """
    # 加载原始数据
    dataset_dict = create_train_dataset(
        train_path=config["train_data"],
        val_path=config.get("val_data"),
        tokenizer=tokenizer,
        max_samples=config.get("max_train_samples")
    )
    
    # Tokenization
    logger.info("Tokenizing datasets...")
    tokenized_datasets = dataset_dict.map(
        lambda examples: tokenize_function(
            examples,
            tokenizer=tokenizer,
            max_length=config.get("max_seq_length", 4096),
            train_on_inputs=config.get("train_on_inputs", False)
        ),
        batched=True,
        remove_columns=dataset_dict["train"].column_names,
        desc="Tokenizing"
    )
    
    logger.info(f"Training samples: {len(tokenized_datasets['train'])}")
    if "validation" in tokenized_datasets:
        logger.info(f"Validation samples: {len(tokenized_datasets['validation'])}")
    
    return tokenized_datasets
