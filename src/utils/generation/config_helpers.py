"""
Configuration Helpers - 统一配置解析工具

提供从 Config 对象解析各类配置的辅助函数，减少生成器 __init__ 中的重复代码。
"""
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CoverageConfig:
    """覆盖率/多样性配置"""
    mode: str = "hybrid"
    constraint_strength: str = "hybrid"
    targets: dict = field(default_factory=dict)
    template_name: str | None = None
    intent_targets: dict = field(default_factory=dict)
    # Diversity
    diversity_mode: str = "off"
    question_type_targets: dict = field(default_factory=dict)
    # Scenario injection
    scenario_mode: str = "off"
    fuzzy_ratio: float = 0.0
    templates_path: str | None = None
    # Negative sampling
    negative_ratio: float | None = None
    negative_types: list = field(default_factory=list)


@dataclass
class RetrievalConfig:
    """检索配置"""
    mode: str = "hybrid"
    min_score: float = 0.0
    fallback_top_k: int = 6
    # Call chain
    call_chain_enabled: bool = False
    call_chain_max_depth: int = 1
    call_chain_max_expansion: int = 20


@dataclass
class ConstraintsConfig:
    """约束配置"""
    enable_counterexample: bool = False
    enable_arch_constraints: bool = False
    architecture_constraints: list = field(default_factory=list)


@dataclass
class OutputPaths:
    """输出路径配置"""
    output_jsonl: Path = field(default_factory=lambda: Path("data/intermediate/output.jsonl"))
    rejected_jsonl: Path | None = None
    
    def ensure_dirs(self):
        """确保目录存在"""
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        if self.rejected_jsonl:
            self.rejected_jsonl.parent.mkdir(parents=True, exist_ok=True)


def parse_coverage_config(config, section: str) -> CoverageConfig:
    """解析覆盖率/多样性配置
    
    Args:
        config: Config 对象
        section: 配置节名 (如 'question_answer', 'design_questions')
        
    Returns:
        CoverageConfig: 解析后的配置
    """
    coverage_dict = config.get(f'{section}.coverage', {}) or {}
    diversity_dict = coverage_dict.get('diversity', {}) or {}
    scenario_dict = coverage_dict.get('scenario_injection', {}) or {}
    
    negative_types = coverage_dict.get('negative_types', [])
    if not isinstance(negative_types, list):
        negative_types = []
    
    return CoverageConfig(
        mode=coverage_dict.get('mode', 'hybrid'),
        constraint_strength=coverage_dict.get('constraint_strength', 'hybrid'),
        targets=coverage_dict.get('targets', {}) or {},
        template_name=coverage_dict.get('template_name'),
        intent_targets=coverage_dict.get('intent_targets', {}) or {},
        diversity_mode=diversity_dict.get('mode', 'off'),
        question_type_targets=diversity_dict.get('question_type_targets', {}) or {},
        scenario_mode=scenario_dict.get('mode', 'off'),
        fuzzy_ratio=float(scenario_dict.get('fuzzy_ratio', 0) or 0),
        templates_path=scenario_dict.get('templates_path'),
        negative_ratio=coverage_dict.get('negative_ratio'),
        negative_types=negative_types,
    )


def parse_retrieval_config(config, section: str, default_top_k: int = 6) -> RetrievalConfig:
    """解析检索配置
    
    Args:
        config: Config 对象
        section: 配置节名
        default_top_k: 默认 top_k 值
        
    Returns:
        RetrievalConfig: 解析后的配置
    """
    retrieval_dict = config.get(f'{section}.retrieval', {}) or {}
    call_chain_dict = retrieval_dict.get('call_chain', {}) or {}
    
    return RetrievalConfig(
        mode=retrieval_dict.get('mode', 'hybrid'),
        min_score=float(retrieval_dict.get('min_score', 0.0)),
        fallback_top_k=int(retrieval_dict.get('fallback_top_k', default_top_k)),
        call_chain_enabled=bool(call_chain_dict.get('enabled', False)),
        call_chain_max_depth=int(call_chain_dict.get('max_depth', 1)),
        call_chain_max_expansion=int(call_chain_dict.get('max_expansion', 20)),
    )


def parse_constraints_config(config, section: str) -> ConstraintsConfig:
    """解析约束配置
    
    Args:
        config: Config 对象
        section: 配置节名
        
    Returns:
        ConstraintsConfig: 解析后的配置
    """
    from src.utils.io.file_ops import load_yaml_file
    
    constraints_dict = config.get(f'{section}.constraints', {}) or {}
    constraints_path = config.get('core.architecture_constraints_path')
    
    # 加载架构约束
    arch_constraints = []
    if constraints_path:
        data = load_yaml_file(constraints_path)
        if data:
            if isinstance(data, dict):
                items = data.get('constraints', [])
            else:
                items = data
            if isinstance(items, list):
                arch_constraints = [item for item in items if isinstance(item, str) and item.strip()]
        else:
            logger.warning("Architecture constraints not found: %s", constraints_path)
    
    return ConstraintsConfig(
        enable_counterexample=bool(constraints_dict.get('enable_counterexample', False)),
        enable_arch_constraints=bool(constraints_dict.get('enable_arch_constraints', False)),
        architecture_constraints=arch_constraints,
    )


def parse_output_paths(
    config,
    output_key: str,
    output_default: str,
    rejected_key: str | None = None,
    rejected_default: str | None = None
) -> OutputPaths:
    """解析输出路径配置
    
    Args:
        config: Config 对象
        output_key: 输出路径配置键
        output_default: 默认输出路径
        rejected_key: 拒绝文件配置键
        rejected_default: 默认拒绝文件路径
        
    Returns:
        OutputPaths: 解析后的路径
    """
    output_path = Path(config.get(output_key, output_default))
    rejected_path = None
    if rejected_key:
        rejected_path = Path(config.get(rejected_key, rejected_default))
    
    paths = OutputPaths(output_jsonl=output_path, rejected_jsonl=rejected_path)
    paths.ensure_dirs()
    return paths


def create_seeded_rng(config, key: str = 'core.seed', default: int = 42) -> random.Random:
    """创建带种子的随机数生成器
    
    Args:
        config: Config 对象
        key: 种子配置键
        default: 默认种子值
        
    Returns:
        random.Random: 随机数生成器
    """
    seed = config.get(key, default)
    return random.Random(seed)


def get_with_fallback(config, primary_key: str, fallback_key: str, default: Any = None) -> Any:
    """带回退的配置获取
    
    Args:
        config: Config 对象
        primary_key: 主配置键
        fallback_key: 回退配置键
        default: 默认值
        
    Returns:
        配置值
    """
    value = config.get(primary_key)
    if value is not None:
        return value
    return config.get(fallback_key, default)


def resolve_design_limit(config, default: int = 50) -> int:
    """Resolve design limits from config, using the smallest configured value."""
    max_questions = config.get("design_questions.max_questions")
    max_samples = get_with_fallback(config, "design_questions.max_samples", "core.max_items", None)

    def _coerce_limit(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    max_questions = _coerce_limit(max_questions)
    max_samples = _coerce_limit(max_samples)

    limits = [limit for limit in (max_questions, max_samples) if limit is not None]
    if not limits:
        return int(default)

    effective = min(limits)
    if max_questions is not None and max_samples is not None and max_questions != max_samples:
        logger.warning(
            "Design limits differ: max_questions=%s, max_samples=%s; using min=%s",
            max_questions,
            max_samples,
            effective,
        )
    return effective


def resolve_prompt_path(preferred: str | None, fallback: str) -> str:
    """解析 prompt 模板路径
    
    Args:
        preferred: 优先路径（可能不存在）
        fallback: 回退路径
        
    Returns:
        str: 实际可用的路径
    """
    if preferred:
        preferred_path = Path(preferred)
        if preferred_path.exists():
            return str(preferred_path)
        logger.warning("Preferred prompt not found, fallback: %s", preferred_path)
    return fallback
