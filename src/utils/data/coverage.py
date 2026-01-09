"""
Coverage Utilities - 覆盖率标记与采样相关工具

提供覆盖率桶推断、意图推断、分布计算等通用函数。
"""
from collections import defaultdict
from typing import Any

from src.utils.data.validator import normalize_path_separators


# 意图关键词映射
INTENT_KEYWORDS = {
    "config": ["config", "yaml", "properties", "flag", "env", "配置", "开关"],
    "error": ["error", "exception", "fail", "timeout", "retry", "code", "错误", "异常", "失败", "超时", "重试", "错误码"],
    "deploy": ["deploy", "rollout", "release", "migration", "部署", "发布", "上线", "迁移"],
    "impact": ["impact", "change", "break", "影响", "变更"],
    "perf": ["latency", "throughput", "performance", "perf", "性能", "吞吐", "延迟"],
    "consistency": ["consistency", "transaction", "一致性", "事务"],
    "auth": ["auth", "authorize", "permission", "权限", "鉴权", "认证"],
    "flow": ["flow", "workflow", "流程", "链路", "路径"],
    "how_to": ["how to", "如何", "怎样", "如何做", "如何使用"],
    "compatibility": ["compatibility", "legacy", "兼容", "历史"],
    "edge": ["edge", "corner", "边界", "极端"],
}

# 困难样本关键词
HARD_KEYWORDS = [
    "legacy",
    "compatibility",
    "invariant",
    "gotcha",
    "pitfall",
    "反直觉",
    "隐含",
    "历史",
    "兼容",
    "坑",
    "陷阱",
]

# 标准覆盖率桶
BUCKETS = ("high", "mid", "hard")

# 默认覆盖率目标
DEFAULT_TARGETS = {"high": 0.8, "mid": 0.15, "hard": 0.05}

# 回退链（当某个桶样本不足时，从哪些桶借用）
FALLBACK_CHAIN = {
    "hard": ("mid", "high"),
    "mid": ("high",),
    "high": (),
}


def infer_intent(text: str) -> str:
    """从文本推断意图类型
    
    Args:
        text: 问题或答案文本
        
    Returns:
        str: 推断的意图类型
    """
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return intent
    return "how_to"


def infer_module_span(evidence_refs: list[dict]) -> str:
    """从证据引用推断模块跨度
    
    Args:
        evidence_refs: 证据引用列表
        
    Returns:
        str: "single" 或 "multi"
    """
    if not evidence_refs:
        return "single"
    
    prefixes = set()
    for ref in evidence_refs:
        path = ref.get("file_path") or ""
        if not path:
            continue
        normalized = normalize_path_separators(path)
        prefix = normalized.split("/")[0] if normalized else ""
        if prefix:
            prefixes.add(prefix)
    
    return "multi" if len(prefixes) > 1 else "single"


def infer_bucket(intent: str, module_span: str, text: str) -> str:
    """推断覆盖率桶
    
    Args:
        intent: 意图类型
        module_span: 模块跨度
        text: 文本内容
        
    Returns:
        str: "high", "mid", 或 "hard"
    """
    lowered = text.lower()
    if intent in ("compatibility", "edge") or any(kw in lowered for kw in HARD_KEYWORDS):
        return "hard"
    if module_span == "multi" or intent in ("perf", "consistency"):
        return "mid"
    return "high"


def apply_evidence_bucket(
    bucket: str,
    evidence_count: int,
    evidence_cfg: dict,
) -> str:
    """基于证据数量调整覆盖率桶
    
    Args:
        bucket: 初始桶
        evidence_count: 证据数量
        evidence_cfg: 证据配置 {mode, mid_min, hard_min}
        
    Returns:
        str: 调整后的桶
    """
    mode = evidence_cfg.get("mode", "off")
    if mode not in ("assist", "strict"):
        return bucket

    try:
        mid_min = int(evidence_cfg.get("mid_min", 0))
    except (TypeError, ValueError):
        mid_min = 0
    try:
        hard_min = int(evidence_cfg.get("hard_min", 0))
    except (TypeError, ValueError):
        hard_min = 0

    if mode == "strict":
        if hard_min and evidence_count >= hard_min:
            return "hard"
        if mid_min and evidence_count >= mid_min:
            return "mid"
        return "high"

    # assist mode
    candidate = bucket
    if hard_min and evidence_count >= hard_min:
        candidate = "hard"
    elif mid_min and evidence_count >= mid_min:
        candidate = "mid"

    rank = {"high": 0, "mid": 1, "hard": 2}
    base_rank = rank.get(bucket, 0)
    cand_rank = rank.get(candidate, base_rank)
    return candidate if cand_rank > base_rank else bucket


def compute_distribution(samples: list[dict], field_path: str = "quality.coverage.bucket") -> dict:
    """计算样本分布
    
    Args:
        samples: 样本列表
        field_path: 要统计的字段路径 (点分隔)
        
    Returns:
        dict: {counts: {}, ratios: {}, total: int}
    """
    counts: dict[str, int] = {}
    
    for sample in samples:
        # 按路径获取值
        value = sample
        for key in field_path.split("."):
            if isinstance(value, dict):
                value = value.get(key, {})
            else:
                value = None
                break
        
        if value is None or isinstance(value, dict):
            value = "unknown"
        
        counts[value] = counts.get(value, 0) + 1
    
    total = sum(counts.values())
    ratios = {}
    if total > 0:
        ratios = {key: round(value / total, 4) for key, value in counts.items()}
    
    return {"counts": counts, "ratios": ratios, "total": total}


def compute_multi_distributions(samples: list[dict]) -> dict:
    """计算多维度分布（bucket, intent, module_span, polarity）
    
    Args:
        samples: 样本列表
        
    Returns:
        dict: 包含各维度分布的字典
    """
    total = len(samples)
    bucket_counts: dict[str, int] = defaultdict(int)
    intent_counts: dict[str, int] = defaultdict(int)
    module_counts: dict[str, int] = defaultdict(int)
    polarity_counts: dict[str, int] = defaultdict(int)

    for sample in samples:
        coverage = sample.get("quality", {}).get("coverage", {})
        bucket = coverage.get("bucket") or "high"
        intent = coverage.get("intent") or "unknown"
        module_span = coverage.get("module_span") or "unknown"
        polarity = coverage.get("polarity") or "positive"

        bucket_counts[bucket] += 1
        intent_counts[intent] += 1
        module_counts[module_span] += 1
        polarity_counts[polarity] += 1

    def ratios(counts: dict[str, int]) -> dict[str, float]:
        if total == 0:
            return {}
        return {key: round(value / total, 4) for key, value in counts.items()}

    return {
        "bucket_distribution": {
            "counts": dict(bucket_counts),
            "ratios": ratios(bucket_counts),
        },
        "intent_distribution": {
            "counts": dict(intent_counts),
            "ratios": ratios(intent_counts),
        },
        "module_span_distribution": {
            "counts": dict(module_counts),
            "ratios": ratios(module_counts),
        },
        "polarity_distribution": {
            "counts": dict(polarity_counts),
            "ratios": ratios(polarity_counts),
        },
    }


def normalize_targets(targets: dict | None) -> tuple[dict[str, float], bool]:
    """归一化覆盖率目标
    
    Args:
        targets: 原始目标 {bucket: ratio}
        
    Returns:
        tuple: (归一化后的目标, 是否使用了默认值)
    """
    if not isinstance(targets, dict):
        return DEFAULT_TARGETS.copy(), True
    total = sum(float(value) for value in targets.values())
    if total <= 0:
        return DEFAULT_TARGETS.copy(), True
    normalized = {bucket: float(targets.get(bucket, 0.0)) / total for bucket in BUCKETS}
    return normalized, False


def desired_counts(total: int, targets: dict[str, float]) -> dict[str, int]:
    """计算每个桶的期望数量
    
    Args:
        total: 总样本数
        targets: 归一化后的目标
        
    Returns:
        dict: {bucket: count}
    """
    counts = {bucket: int(round(total * targets.get(bucket, 0.0))) for bucket in BUCKETS}
    delta = total - sum(counts.values())
    if delta != 0:
        ordered = sorted(targets.items(), key=lambda item: item[1], reverse=True)
        idx = 0
        step = 1 if delta > 0 else -1
        for _ in range(abs(delta)):
            bucket = ordered[idx % len(ordered)][0]
            counts[bucket] = max(0, counts[bucket] + step)
            idx += 1
    return counts
