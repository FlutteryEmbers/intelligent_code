#!/usr/bin/env python3
"""
模型评测脚本

Usage:
    python eval.py                                    # 使用默认路径
    python eval.py --checkpoint ../checkpoints/xxx    # 自定义checkpoint
    python eval.py --max-samples 10                   # 只评测10个样本
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_model_and_tokenizer(checkpoint_dir: str, base_model_path: str = None):
    """加载模型和 tokenizer（支持 LoRA adapter）"""
    checkpoint_path = Path(checkpoint_dir).resolve()
    
    # 检查是否是 LoRA checkpoint
    adapter_config = checkpoint_path / "adapter_config.json"
    is_lora = adapter_config.exists()
    
    if is_lora:
        logger.info("Loading LoRA adapter...")
        # 从 adapter_config 读取 base model 路径
        with open(adapter_config) as f:
            config = json.load(f)
            base_model_path = base_model_path or config.get("base_model_name_or_path")
        
        # 解析 base model 路径
        if base_model_path:
            base_model_path_obj = Path(base_model_path)
            # 如果是本地路径，转换为绝对路径
            if base_model_path_obj.exists():
                base_model_path = str(base_model_path_obj.resolve())
        
        logger.info(f"Base model: {base_model_path}")
        
        # 判断是否为本地路径
        is_local_base = Path(base_model_path).exists()
        
        # 加载 base model
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=is_local_base
        )
        
        # 加载 LoRA adapter
        model = PeftModel.from_pretrained(base_model, str(checkpoint_path))
        tokenizer = AutoTokenizer.from_pretrained(
            base_model_path,
            local_files_only=is_local_base
        )
    else:
        logger.info("Loading full model...")
        model = AutoModelForCausalLM.from_pretrained(
            str(checkpoint_path),
            torch_dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=True
        )
        tokenizer = AutoTokenizer.from_pretrained(
            str(checkpoint_path),
            local_files_only=True
        )
    
    model.eval()
    return model, tokenizer


def load_eval_data(data_path: str) -> List[Dict]:
    """加载评测数据"""
    data_path = Path(data_path).resolve()
    samples = []
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def generate_response(model, tokenizer, messages: List[Dict], max_new_tokens: int = 1024) -> str:
    """生成回复"""
    # 应用 chat template
    prompt = tokenizer.apply_chat_template(
        messages[:-1],  # 不包含 assistant 的消息
        tokenize=False,
        add_generation_prompt=True
    )
    
    # Tokenize
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    
    # 生成
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.7,
            top_p=0.95,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id
        )
    
    # 解码（只保留生成的部分）
    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response


def compute_metrics(predictions: List[str], references: List[str]) -> Dict:
    """计算评测指标（简单版本）"""
    # 这里可以添加更复杂的指标（BLEU, ROUGE等）
    total = len(predictions)
    exact_matches = sum(1 for pred, ref in zip(predictions, references) if pred.strip() == ref.strip())
    
    return {
        "total_samples": total,
        "exact_match": exact_matches,
        "exact_match_rate": exact_matches / total if total > 0 else 0
    }


def evaluate(model, tokenizer, eval_data: List[Dict], output_file: str = None, max_samples: int = None):
    """执行评测"""
    if max_samples:
        eval_data = eval_data[:max_samples]
    
    logger.info(f"Evaluating on {len(eval_data)} samples...")
    
    predictions = []
    references = []
    results = []
    
    for sample in tqdm(eval_data, desc="Evaluating"):
        messages = sample["messages"]
        
        # 提取reference（最后一条assistant消息）
        reference = messages[-1]["content"] if messages[-1]["role"] == "assistant" else ""
        
        # 生成预测
        prediction = generate_response(model, tokenizer, messages)
        
        predictions.append(prediction)
        references.append(reference)
        
        # 记录结果
        results.append({
            "messages": messages,
            "prediction": prediction,
            "reference": reference
        })
    
    # 计算指标
    metrics = compute_metrics(predictions, references)
    
    logger.info("\n📊 Evaluation Metrics:")
    for key, value in metrics.items():
        logger.info(f"  {key}: {value}")
    
    # 保存结果
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
        
        logger.info(f"\n💾 Results saved to: {output_path}")
    
    return metrics


def main():
    # 获取脚本所在目录（fine_tuning目录）
    script_dir = Path(__file__).parent
    # 项目根目录（fine_tuning的父目录）
    project_root = script_dir.parent
    
    parser = argparse.ArgumentParser(
        description="Evaluate fine-tuned model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 使用默认路径评测
  python eval.py
  
  # 自定义checkpoint
  python eval.py --checkpoint ../checkpoints/lora-qwen2.5-coder-3b
  
  # 只评测10个样本（快速测试）
  python eval.py --max-samples 10
        """
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to checkpoint directory (default: ../checkpoints/lora-qwen2.5-coder-1.5b)"
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Path to evaluation data (default: ../data/final/val_sft.jsonl)"
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default=None,
        help="Base model path (only needed if not in adapter_config.json)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for evaluation results (default: ../data/eval_results.jsonl)"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Maximum number of samples to evaluate"
    )
    
    args = parser.parse_args()
    
    # 设置默认路径（相对于项目根目录）
    checkpoint_path = args.checkpoint or str((project_root / "checkpoints" / "lora-qwen2.5-coder-1.5b").resolve())
    data_path = args.data or str((project_root / "data" / "final" / "val_sft.jsonl").resolve())
    output_path = args.output or str((project_root / "data" / "eval_results.jsonl").resolve())
    
    logger.info(f"Checkpoint: {checkpoint_path}")
    logger.info(f"Data: {data_path}")
    logger.info(f"Output: {output_path}")
    
    # 检查文件是否存在
    if not Path(checkpoint_path).exists():
        logger.error(f"❌ Checkpoint not found: {checkpoint_path}")
        logger.info("\n💡 Hint: Train a model first using: python train.py configs/lora_1.5b.yaml")
        sys.exit(1)
    
    if not Path(data_path).exists():
        logger.error(f"❌ Data file not found: {data_path}")
        sys.exit(1)
    
    # 加载模型
    logger.info("Loading model...")
    model, tokenizer = load_model_and_tokenizer(
        checkpoint_path,
        args.base_model
    )
    
    # 加载评测数据
    logger.info("Loading evaluation data...")
    eval_data = load_eval_data(data_path)
    
    # 评测
    results = evaluate(
        model=model,
        tokenizer=tokenizer,
        eval_data=eval_data,
        output_file=output_path,
        max_samples=args.max_samples
    )
    
    logger.info("\n✅ Evaluation completed!")


if __name__ == "__main__":
    main()
