"""
Export utilities for converting TrainingSample to SFT formats.
Provides export to Qwen2.5 and other model fine-tuning formats.
"""
from pathlib import Path
from typing import Any

from .io import write_jsonl


def export_sft_jsonl(
    samples: list[dict],
    out_path: Path | str,
    system_prompt: str = None
) -> None:
    """
    Export TrainingSample objects to Qwen2.5 SFT format (messages JSONL).
    
    Format per line:
    {
      "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
      ],
      "metadata": {
        "scenario": "...",
        "repo_commit": "...",
        "evidence_refs": [...],
        "quality": {...}
      }
    }
    
    Note: The assistant content does NOT include thought/reasoning trace
    to prevent the model from learning to output internal reasoning.
    
    Args:
        samples: List of TrainingSample dicts
        out_path: Output JSONL file path
        system_prompt: System prompt (if None, uses default)
    """
    out_path = Path(out_path)
    
    # Default system prompt
    if system_prompt is None:
        system_prompt = (
            "你是一个专业的代码助手，精通 Java 开发和架构设计。"
            "你的任务是根据提供的代码上下文，准确回答问题或提供设计方案。"
            "你必须基于 evidence（证据）进行推理，确保答案可追溯到具体代码。"
        )
    
    # Convert samples to SFT format
    sft_samples = []
    
    for sample in samples:
        # Extract fields
        instruction = sample.get("instruction", "")
        context = sample.get("context", "")
        answer = sample.get("answer", "")
        scenario = sample.get("scenario", "unknown")
        repo_commit = sample.get("repo_commit", "UNKNOWN_COMMIT")
        
        # Extract evidence_refs from thought
        thought = sample.get("thought", {})
        evidence_refs = thought.get("evidence_refs", [])
        
        # Extract quality info (if exists)
        quality = sample.get("quality", {})
        
        # Build user content (instruction + context)
        user_content = instruction
        if context:
            user_content += f"\n\n代码上下文：\n{context}"
        
        # Build SFT sample
        sft_sample = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                },
                {
                    "role": "assistant",
                    "content": answer
                }
            ],
            "metadata": {
                "scenario": scenario,
                "repo_commit": repo_commit,
                "evidence_refs": evidence_refs,
                "quality": quality
            }
        }
        
        sft_samples.append(sft_sample)
    
    # Write to file
    write_jsonl(out_path, sft_samples)
    
    print(f"Exported {len(sft_samples)} samples to {out_path}")


def export_alpaca_jsonl(
    samples: list[dict],
    out_path: Path | str
) -> None:
    """
    Export TrainingSample objects to Alpaca format (instruction-input-output).
    
    Format per line:
    {
      "instruction": "...",
      "input": "...",  (context)
      "output": "...",
      "metadata": {...}
    }
    
    Args:
        samples: List of TrainingSample dicts
        out_path: Output JSONL file path
    """
    out_path = Path(out_path)
    
    alpaca_samples = []
    
    for sample in samples:
        instruction = sample.get("instruction", "")
        context = sample.get("context", "")
        answer = sample.get("answer", "")
        scenario = sample.get("scenario", "unknown")
        repo_commit = sample.get("repo_commit", "UNKNOWN_COMMIT")
        
        # Extract evidence_refs from thought
        thought = sample.get("thought", {})
        evidence_refs = thought.get("evidence_refs", [])
        
        alpaca_sample = {
            "instruction": instruction,
            "input": context,
            "output": answer,
            "metadata": {
                "scenario": scenario,
                "repo_commit": repo_commit,
                "evidence_refs": evidence_refs
            }
        }
        
        alpaca_samples.append(alpaca_sample)
    
    write_jsonl(out_path, alpaca_samples)
    
    print(f"Exported {len(alpaca_samples)} samples to {out_path} (Alpaca format)")


def export_with_reasoning_trace(
    samples: list[dict],
    out_path: Path | str,
    system_prompt: str = None
) -> None:
    """
    Export TrainingSample with reasoning trace included in assistant output.
    
    This format is useful for:
    - Training models to output reasoning steps
    - Evaluation and debugging
    - Chain-of-thought fine-tuning
    
    Format: Same as export_sft_jsonl but assistant content includes thought.
    
    Args:
        samples: List of TrainingSample dicts
        out_path: Output JSONL file path
        system_prompt: System prompt (if None, uses default)
    """
    out_path = Path(out_path)
    
    if system_prompt is None:
        system_prompt = (
            "你是一个专业的代码助手，精通 Java 开发和架构设计。"
            "你的任务是根据提供的代码上下文，准确回答问题或提供设计方案。"
            "在回答时，请先展示你的推理过程，然后给出最终答案。"
        )
    
    sft_samples = []
    
    for sample in samples:
        instruction = sample.get("instruction", "")
        context = sample.get("context", "")
        answer = sample.get("answer", "")
        thought = sample.get("thought", {})
        scenario = sample.get("scenario", "unknown")
        repo_commit = sample.get("repo_commit", "UNKNOWN_COMMIT")
        
        # Build user content
        user_content = instruction
        if context:
            user_content += f"\n\n代码上下文：\n{context}"
        
        # Build assistant content with reasoning
        assistant_content = "## 推理过程\n\n"
        
        # Add observations
        observations = thought.get("observations", [])
        if observations:
            assistant_content += "### 观察\n"
            for obs in observations:
                assistant_content += f"- {obs}\n"
            assistant_content += "\n"
        
        # Add inferences
        inferences = thought.get("inferences", [])
        if inferences:
            assistant_content += "### 推断\n"
            for inf in inferences:
                assistant_content += f"- {inf}\n"
            assistant_content += "\n"
        
        # Add assumptions
        assumptions = thought.get("assumptions", [])
        if assumptions:
            assistant_content += "### 假设\n"
            for assump in assumptions:
                assistant_content += f"- {assump}\n"
            assistant_content += "\n"
        
        # Add final answer
        assistant_content += "## 最终答案\n\n"
        assistant_content += answer
        
        sft_sample = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                },
                {
                    "role": "assistant",
                    "content": assistant_content
                }
            ],
            "metadata": {
                "scenario": scenario,
                "repo_commit": repo_commit,
                "evidence_refs": thought.get("evidence_refs", [])
            }
        }
        
        sft_samples.append(sft_sample)
    
    write_jsonl(out_path, sft_samples)
    
    print(f"Exported {len(sft_samples)} samples with reasoning trace to {out_path}")


def export_statistics(
    samples: list[dict],
    out_path: Path | str
) -> dict[str, Any]:
    """
    Generate and export statistics about the dataset.
    
    Args:
        samples: List of TrainingSample dicts
        out_path: Output JSON file path
        
    Returns:
        Statistics dict
    """
    from .io import write_json
    
    if not samples:
        stats = {"total": 0, "error": "No samples"}
        write_json(out_path, stats)
        return stats
    
    # Count by scenario
    scenario_counts = {}
    for sample in samples:
        scenario = sample.get("scenario", "unknown")
        scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
    
    # Calculate length statistics
    instruction_lengths = [len(s.get("instruction", "")) for s in samples]
    context_lengths = [len(s.get("context", "")) for s in samples]
    answer_lengths = [len(s.get("answer", "")) for s in samples]
    
    # Evidence refs statistics
    evidence_counts = []
    for sample in samples:
        thought = sample.get("thought", {})
        evidence_refs = thought.get("evidence_refs", [])
        evidence_counts.append(len(evidence_refs))
    
    stats = {
        "total_samples": len(samples),
        "scenario_distribution": scenario_counts,
        "length_stats": {
            "instruction": {
                "min": min(instruction_lengths) if instruction_lengths else 0,
                "max": max(instruction_lengths) if instruction_lengths else 0,
                "avg": sum(instruction_lengths) / len(instruction_lengths) if instruction_lengths else 0
            },
            "context": {
                "min": min(context_lengths) if context_lengths else 0,
                "max": max(context_lengths) if context_lengths else 0,
                "avg": sum(context_lengths) / len(context_lengths) if context_lengths else 0
            },
            "answer": {
                "min": min(answer_lengths) if answer_lengths else 0,
                "max": max(answer_lengths) if answer_lengths else 0,
                "avg": sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0
            }
        },
        "evidence_refs": {
            "min": min(evidence_counts) if evidence_counts else 0,
            "max": max(evidence_counts) if evidence_counts else 0,
            "avg": sum(evidence_counts) / len(evidence_counts) if evidence_counts else 0
        }
    }
    
    write_json(out_path, stats)
    
    # Print summary
    print("=" * 70)
    print(" Dataset Statistics")
    print("=" * 70)
    print(f"Total samples: {stats['total_samples']}")
    print()
    print("Scenario distribution:")
    for scenario, count in scenario_counts.items():
        pct = count / stats['total_samples'] * 100
        print(f"  {scenario}: {count} ({pct:.1f}%)")
    print()
    print(f"Avg instruction length: {stats['length_stats']['instruction']['avg']:.0f} chars")
    print(f"Avg context length: {stats['length_stats']['context']['avg']:.0f} chars")
    print(f"Avg answer length: {stats['length_stats']['answer']['avg']:.0f} chars")
    print(f"Avg evidence refs: {stats['evidence_refs']['avg']:.1f}")
    print("=" * 70)
    
    return stats
