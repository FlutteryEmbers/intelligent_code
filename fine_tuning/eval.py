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
import yaml
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


def load_model_and_tokenizer(checkpoint_dir: str, base_model_path: str = None, only_base: bool = False):
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
        
        if only_base:
            logger.info(f"Loading BASE model (no adapter): {base_model_path}")
            # 加载 base model
            model = AutoModelForCausalLM.from_pretrained(
                base_model_path,
                dtype=torch.bfloat16,
                device_map="auto",
                local_files_only=is_local_base
            )
            tokenizer = AutoTokenizer.from_pretrained(
                base_model_path,
                local_files_only=is_local_base
            )
            model.eval()
            return model, tokenizer

        # 加载 base model
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_path,
            dtype=torch.bfloat16,
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
            dtype=torch.bfloat16,
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


from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer
import nltk

# Ensure punkt resources are downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)

def compute_metrics(predictions: List[str], references: List[str]) -> Dict:
    """计算评测指标（包括 Exact Match, BLEU, Rouge）"""
    total = len(predictions)
    if total == 0:
        return {}

    # Exact Match
    exact_matches = sum(1 for pred, ref in zip(predictions, references) if pred.strip() == ref.strip())
    
    # Rouge
    scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
    rouge_scores = {'rouge1': 0.0, 'rouge2': 0.0, 'rougeL': 0.0}
    
    # BLEU
    bleu_score = 0.0
    smoothing = SmoothingFunction().method1
    
    for pred, ref in zip(predictions, references):
        # Rouge
        scores = scorer.score(ref, pred)
        for key in rouge_scores:
            rouge_scores[key] += scores[key].fmeasure
            
        # BLEU (simple tokenizer)
        ref_tokens = nltk.word_tokenize(ref)
        pred_tokens = nltk.word_tokenize(pred)
        bleu_score += sentence_bleu([ref_tokens], pred_tokens, smoothing_function=smoothing)
    
    # Average scores
    metrics = {
        "total_samples": total,
        "exact_match_rate": exact_matches / total,
        "bleu": bleu_score / total,
    }
    for key in rouge_scores:
        metrics[key] = rouge_scores[key] / total
        
    return metrics


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
    
    return metrics, results


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
        "--config",
        type=str,
        default=None,
        help="Path to training config file (e.g. configs/lora_1.5b.yaml)"
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to checkpoint directory (overrides config)"
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
    
    parser.add_argument(
        "--no-compare-base",
        action="store_false",
        dest="compare_base",
        help="Disable comparison with base model",
        default=True
    )

    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Output markdown report file (default: ../data/eval_report.md)"
    )
    
    args = parser.parse_args()
    
    # 如果指定了 config，从 config 读取 checkpoint 路径
    config_checkpoint = None
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # 解析 output_dir
                output_dir = Path(config.get("output_dir", ""))
                base_dir = config_path.parent.parent
                if output_dir and not output_dir.is_absolute():
                    config_checkpoint = str((base_dir / output_dir).resolve())
                elif output_dir:
                    config_checkpoint = str(output_dir)
        else:
            logger.warning(f"Config file not found: {args.config}")

    # 设置默认路径（优先使用命令行参数，其次是 config 中的路径，最后是默认硬编码路径）
    # 注意：checkpoints 在 fine_tuning/checkpoints 目录下，即 script_dir / "checkpoints"
    default_checkpoint = (script_dir / "checkpoints" / "lora-qwen2.5-coder-1.5b").resolve()
    checkpoint_path = args.checkpoint or config_checkpoint or str(default_checkpoint)
    data_path = args.data or str((project_root / "assets" / "data" / "final" / "val_sft.jsonl").resolve())
    output_path = args.output or str((project_root / "assets" / "data" / "eval_results.jsonl").resolve())
    report_path = args.report or str((project_root / "assets" / "data" / "eval_report.md").resolve())
    
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
    metrics, ft_results = evaluate(
        model=model,
        tokenizer=tokenizer,
        eval_data=eval_data,
        output_file=output_path,
        max_samples=args.max_samples
    )
    
    logger.info("\n✅ Evaluation completed!")

    if args.compare_base:
        logger.info("\n🔄 cleaning up to run BASE model evaluation...")
        del model
        torch.cuda.empty_cache()
        import gc
        gc.collect()
        
        logger.info("loading BASE model...")
        base_model, base_tokenizer = load_model_and_tokenizer(
            checkpoint_path,
            args.base_model,
            only_base=True
        )
        
        logger.info("\n📉 Evaluating BASE model...")
        base_metrics, base_results = evaluate(
            model=base_model,
            tokenizer=base_tokenizer,
            eval_data=eval_data,
            output_file=None, # Don't overwrite main results
            max_samples=args.max_samples
        )
        
        logger.info("\n📊 Comparison (Fine-tuned vs Base):")
        print(f"{'Metric':<20} | {'Fine-tuned':<15} | {'Base':<15} | {'Diff':<10}")
        print("-" * 65)
        for key in metrics:
            if isinstance(metrics[key], (int, float)):
                ft_val = metrics[key]
                base_val = base_metrics.get(key, 0)
                diff = ft_val - base_val
                print(f"{key:<20} | {ft_val:<15.4f} | {base_val:<15.4f} | {diff:<+10.4f}")

        logger.info("\n📝 Qualitative Comparison Examples:")
        num_examples = min(2, len(ft_results))
        for i in range(num_examples):
            ft_res = ft_results[i]
            base_res = base_results[i]
            
            # Extract question (last user message)
            messages = ft_res['messages']
            question = "N/A"
            for msg in reversed(messages):
                if msg['role'] == 'user':
                    question = msg['content']
                    break
            
            reference = ft_res['reference']
            ft_pred = ft_res['prediction']
            base_pred = base_res['prediction']
            
            print(f"\nExample {i+1}:")
            print(f"❓ Question:\n{question[:200]}..." if len(question) > 200 else f"❓ Question:\n{question}")
            print(f"\n📖 Reference:\n{reference[:200]}..." if len(reference) > 200 else f"\n📖 Reference:\n{reference}")
            print(f"\n🤖 Fine-tuned Model:\n{ft_pred[:200]}..." if len(ft_pred) > 200 else f"\n🤖 Fine-tuned Model:\n{ft_pred}")
        print("-" * 80)

        # Save Markdown Report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# Evaluation Report\n\n")
            f.write(f"**Checkpoint**: `{checkpoint_path}`\n")
            f.write(f"**Base Model**: `{args.base_model or 'Auto-detected'}`\n")
            f.write(f"**Data**: `{data_path}`\n\n")

            f.write("## 📊 Metrics Comparison\n\n")
            f.write("| Metric | Fine-tuned | Base | Diff |\n")
            f.write("| :--- | :--- | :--- | :--- |\n")
            for key in metrics:
                if isinstance(metrics[key], (int, float)):
                    ft_val = metrics[key]
                    base_val = base_metrics.get(key, 0)
                    diff = ft_val - base_val
                    f.write(f"| {key} | {ft_val:.4f} | {base_val:.4f} | {diff:+.4f} |\n")
            
            f.write("\n## 📝 Qualitative Examples\n\n")
            for i in range(min(5, len(ft_results))):
                ft_res = ft_results[i]
                base_res = base_results[i]
                
                # Extract question
                messages = ft_res['messages']
                question = "N/A"
                for msg in reversed(messages):
                    if msg['role'] == 'user':
                        question = msg['content']
                        break
                
                f.write(f"### Example {i+1}\n\n")
                f.write(f"**❓ Question**:\n\n{question}\n\n")
                f.write(f"**📖 Reference**:\n\n{ft_res['reference']}\n\n")
                f.write(f"**🤖 Fine-tuned Model**:\n\n{ft_res['prediction']}\n\n")
                f.write(f"**👶 Base Model**:\n\n{base_res['prediction']}\n\n")
                f.write("---\n\n")
        
        logger.info(f"\n📄 Markdown report saved to: {report_path}")


if __name__ == "__main__":
    main()
