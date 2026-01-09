"""
Sampling Utilities - 采样相关工具

提供加权随机选择、覆盖率采样、负采样等通用采样函数。
"""
import random
from typing import Any

from src.utils.core.logger import get_logger

logger = get_logger(__name__)


def weighted_choice(weights: dict[str, float], default: str, rng: random.Random) -> str:
    """加权随机选择
    
    Args:
        weights: 权重字典 {选项: 权重}
        default: 默认选项
        rng: 随机数生成器
        
    Returns:
        str: 选中的选项
    """
    if not isinstance(weights, dict) or not weights:
        return default
    
    total = sum(float(value) for value in weights.values())
    if total <= 0:
        return default
    
    threshold = rng.random() * total
    cumulative = 0.0
    for key, value in weights.items():
        cumulative += float(value)
        if threshold <= cumulative:
            return key
    return default


def sample_coverage_target(
    coverage_config,
    rng: random.Random
) -> tuple[str, str]:
    """采样覆盖率目标桶和意图
    
    Args:
        coverage_config: CoverageConfig 对象或包含 mode/targets/intent_targets 的 dict
        rng: 随机数生成器
        
    Returns:
        tuple[str, str]: (bucket, intent)
    """
    # 支持 CoverageConfig 对象或 dict
    if hasattr(coverage_config, 'mode'):
        mode = coverage_config.mode
        targets = coverage_config.targets
        intent_targets = coverage_config.intent_targets
    else:
        mode = coverage_config.get('mode', 'hybrid')
        targets = coverage_config.get('targets', {}) or {}
        intent_targets = coverage_config.get('intent_targets', {}) or {}
    
    if mode not in ("upstream", "hybrid"):
        return "high", "how_to"
    
    bucket = weighted_choice(targets, "high", rng)
    intent = weighted_choice(intent_targets, "how_to", rng)
    return bucket, intent


def sample_question_type(
    diversity_config,
    rng: random.Random
) -> str:
    """采样问题类型
    
    Args:
        diversity_config: 多样性配置 (dict 或有 diversity_mode/question_type_targets 属性的对象)
        rng: 随机数生成器
        
    Returns:
        str: 问题类型
    """
    if hasattr(diversity_config, 'diversity_mode'):
        mode = diversity_config.diversity_mode
        targets = diversity_config.question_type_targets
    else:
        mode = diversity_config.get('mode', 'off')
        targets = diversity_config.get('question_type_targets', {}) or {}
    
    if mode != "quota":
        return "how_to"
    return weighted_choice(targets, "how_to", rng)


def sample_negative_type(
    negative_ratio: float | None,
    negative_types: list,
    rng: random.Random
) -> str | None:
    """负采样类型选择
    
    Args:
        negative_ratio: 负样本比例
        negative_types: 负样本类型列表
        rng: 随机数生成器
        
    Returns:
        str | None: 负样本类型，如果不生成负样本则返回 None
    """
    if not negative_types:
        return None
    if not isinstance(negative_ratio, (int, float)):
        return None
    if negative_ratio <= 0:
        return None
    if rng.random() >= float(negative_ratio):
        return None
    return rng.choice(negative_types)


def build_scenario_constraints(
    scenario_config,
    scenario_templates: list,
    rng: random.Random
) -> str:
    """构建场景约束
    
    Args:
        scenario_config: 场景配置 (dict 或有 scenario_mode/fuzzy_ratio 属性的对象)
        scenario_templates: 场景模板列表
        rng: 随机数生成器
        
    Returns:
        str: 场景约束字符串
    """
    if hasattr(scenario_config, 'scenario_mode'):
        mode = scenario_config.scenario_mode
        fuzzy_ratio = scenario_config.fuzzy_ratio
    else:
        mode = scenario_config.get('mode', 'off')
        fuzzy_ratio = float(scenario_config.get('fuzzy_ratio', 0) or 0)
    
    if mode != "ratio":
        return ""
    if not scenario_templates or fuzzy_ratio <= 0:
        return ""
    if rng.random() >= fuzzy_ratio:
        return ""
    return rng.choice(scenario_templates)


def resolve_constraint_strength(constraint_strength: str, bucket: str) -> str:
    """解析约束强度
    
    Args:
        constraint_strength: 配置的约束强度 ('hybrid', 'strong', 'weak')
        bucket: 覆盖率桶
        
    Returns:
        str: 实际约束强度
    """
    if constraint_strength == "hybrid":
        return "strong" if bucket in ("mid", "hard") else "weak"
    if constraint_strength in ("strong", "weak"):
        return constraint_strength
    return "weak"


def build_constraint_rules(constraint_strength: str, bucket: str) -> tuple[str, str]:
    """构建约束规则文本
    
    Args:
        constraint_strength: 配置的约束强度
        bucket: 覆盖率桶
        
    Returns:
        tuple[str, str]: (strength, rules_text)
    """
    strength = resolve_constraint_strength(constraint_strength, bucket)
    
    if strength == "strong":
        rules = (
            "【强约束】\n"
            "- 必须体现冲突/权衡/隐含约束/历史兼容/边界条件中的至少一类。\n"
            "- 问题需指向方法的具体行为或风险，不要停留在泛泛概念。\n"
            "- 至少包含一个明确的限制条件或失败场景。"
        )
    else:
        rules = (
            "【弱约束】\n"
            "- 问题表达清晰、自然，聚焦单一目标或单一流程节点。\n"
            "- 保持与代码上下文相关，但允许更通用的业务表述。"
        )
    return strength, rules


# -----------------------------------------------------------------------------
# 通用采样工具（用于 JSONL 数据）
# -----------------------------------------------------------------------------

def reservoir_sampling(items: list, k: int, seed: int = 42) -> list:
    """蓄水池采样 - 从大数据集中随机采样 k 个元素
    
    Args:
        items: 输入列表
        k: 采样数量
        seed: 随机种子
        
    Returns:
        list: 采样结果
    """
    rng = random.Random(seed)
    
    if len(items) <= k:
        return list(items)
    
    reservoir = list(items[:k])
    
    for i in range(k, len(items)):
        j = rng.randint(0, i)
        if j < k:
            reservoir[j] = items[i]
    
    return reservoir


def stratified_sample_by_scenario(
    samples: list[dict],
    target_per_scenario: int,
    seed: int = 42
) -> list[dict]:
    """按场景分层采样
    
    Args:
        samples: 输入样本列表
        target_per_scenario: 每个场景的目标数量
        seed: 随机种子
        
    Returns:
        list[dict]: 采样结果
    """
    from collections import defaultdict
    
    # 按场景分组
    scenario_groups = defaultdict(list)
    for sample in samples:
        scenario = sample.get("scenario", "unknown")
        scenario_groups[scenario].append(sample)
    
    # 从每个场景采样
    result = []
    for scenario, group in scenario_groups.items():
        sampled = reservoir_sampling(group, target_per_scenario, seed)
        result.extend(sampled)
        logger.info(f"Scenario '{scenario}': sampled {len(sampled)} from {len(group)}")
    
    return result


def sample_by_coverage(
    samples: list[dict],
    coverage_targets: dict[str, float],
    total_target: int,
    seed: int = 42
) -> list[dict]:
    """按覆盖率桶采样
    
    Args:
        samples: 输入样本列表
        coverage_targets: 覆盖率桶目标 {bucket: ratio}
        total_target: 总目标数量
        seed: 随机种子
        
    Returns:
        list[dict]: 采样结果
    """
    from collections import defaultdict
    
    # 按覆盖率桶分组
    bucket_groups = defaultdict(list)
    for sample in samples:
        coverage = sample.get("quality", {}).get("coverage", {})
        bucket = coverage.get("bucket", "unknown")
        bucket_groups[bucket].append(sample)
    
    # 计算每个桶的目标数量
    result = []
    for bucket, ratio in coverage_targets.items():
        target = int(total_target * ratio)
        group = bucket_groups.get(bucket, [])
        sampled = reservoir_sampling(group, target, seed)
        result.extend(sampled)
        logger.info(f"Bucket '{bucket}': sampled {len(sampled)} from {len(group)} (target: {target})")
    
    return result
