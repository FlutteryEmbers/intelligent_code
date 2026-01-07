"""
评测模块 - 自动评测指标和人工评测支持
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

logger = logging.getLogger(__name__)


def load_eval_results(results_path: str) -> List[Dict]:
    """加载评测结果"""
    results = []
    with open(results_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def calculate_metrics(results: List[Dict]) -> Dict:
    """
    计算评测指标
    
    指标包括：
    - BLEU
    - ROUGE
    - 证据引用命中率
    - 平均生成长度
    """
    metrics = {
        "total_samples": len(results),
        "avg_generated_length": 0,
        "avg_reference_length": 0,
        "evidence_hit_rate": 0.0
    }
    
    # 统计长度
    gen_lengths = []
    ref_lengths = []
    evidence_hits = []
    
    for result in results:
        generated = result.get("generated", "")
        reference = result.get("reference", "")
        
        gen_lengths.append(len(generated))
        ref_lengths.append(len(reference))
        
        # 检查证据引用命中率
        evidence_refs = result.get("metadata", {}).get("evidence_refs", [])
        if evidence_refs:
            # 简单检查：生成的文本中是否提到了证据中的关键信息
            # 这里简化为：检查是否包含 symbol_id 中的方法名
            hit = False
            for ref in evidence_refs:
                symbol_id = ref.get("symbol_id", "")
                if ":" in symbol_id:
                    method_name = symbol_id.split(":")[-1]
                    if method_name and method_name in generated:
                        hit = True
                        break
            evidence_hits.append(1 if hit else 0)
    
    metrics["avg_generated_length"] = np.mean(gen_lengths) if gen_lengths else 0
    metrics["avg_reference_length"] = np.mean(ref_lengths) if ref_lengths else 0
    metrics["evidence_hit_rate"] = np.mean(evidence_hits) if evidence_hits else 0
    
    return metrics


def evaluate_by_scenario(results: List[Dict]) -> Dict[str, Dict]:
    """按场景分别评测"""
    scenarios = defaultdict(list)
    
    for result in results:
        scenario = result.get("metadata", {}).get("scenario", "unknown")
        scenarios[scenario].append(result)
    
    scenario_metrics = {}
    for scenario, scenario_results in scenarios.items():
        metrics = calculate_metrics(scenario_results)
        scenario_metrics[scenario] = metrics
    
    return scenario_metrics


def generate_human_eval_samples(
    results: List[Dict],
    output_file: str,
    num_samples: int = 50
) -> None:
    """
    生成人工评测样本集
    
    输出格式：便于人工评分的 JSON 文件
    """
    # 按场景采样
    scenarios = defaultdict(list)
    for result in results:
        scenario = result.get("metadata", {}).get("scenario", "unknown")
        scenarios[scenario].append(result)
    
    # 从每个场景采样
    sampled = []
    samples_per_scenario = num_samples // len(scenarios)
    
    for scenario, scenario_results in scenarios.items():
        # 随机采样
        import random
        samples = random.sample(
            scenario_results,
            min(samples_per_scenario, len(scenario_results))
        )
        
        for i, sample in enumerate(samples):
            eval_item = {
                "id": f"{scenario}_{i+1}",
                "scenario": scenario,
                "instruction": sample["messages"][1]["content"],  # user message
                "context": sample["messages"][0].get("content", ""),  # system message
                "generated": sample["generated"],
                "reference": sample["reference"],
                "ratings": {
                    "correctness": None,  # 1-5
                    "completeness": None,  # 1-5
                    "evidence_usage": None,  # 1-5
                    "clarity": None,  # 1-5
                    "hallucination": None,  # 1-5 (5=无幻觉)
                },
                "comments": ""
            }
            sampled.append(eval_item)
    
    # 保存
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sampled, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Generated {len(sampled)} human evaluation samples")
    logger.info(f"Saved to: {output_path}")


def print_evaluation_report(metrics: Dict, scenario_metrics: Dict[str, Dict] = None):
    """打印评测报告"""
    print("\n" + "="*60)
    print("EVALUATION REPORT")
    print("="*60)
    
    print(f"\n📊 Overall Metrics:")
    print(f"  Total Samples: {metrics['total_samples']}")
    print(f"  Avg Generated Length: {metrics['avg_generated_length']:.1f} chars")
    print(f"  Avg Reference Length: {metrics['avg_reference_length']:.1f} chars")
    print(f"  Evidence Hit Rate: {metrics['evidence_hit_rate']:.2%}")
    
    if scenario_metrics:
        print(f"\n📈 Metrics by Scenario:")
        for scenario, m in scenario_metrics.items():
            print(f"\n  {scenario}:")
            print(f"    Samples: {m['total_samples']}")
            print(f"    Avg Length: {m['avg_generated_length']:.1f} chars")
            print(f"    Evidence Hit Rate: {m['evidence_hit_rate']:.2%}")
    
    print("\n" + "="*60)
