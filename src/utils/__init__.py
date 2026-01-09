"""
工具模块 - 包含数据模型、配置管理等工具
"""

from .schemas import (
    Annotation,
    CodeSymbol,
    EvidenceRef,
    ReasoningTrace,
    TrainingSample,
    ParsingReport,
    sha256_text,
    now_iso,
)
from .config import Config, config, get_config, reload_config
from .logger import get_logger, LoggerManager
from .io import (
    read_json, 
    write_json, 
    read_jsonl, 
    write_jsonl, 
    append_jsonl,
    load_prompt_template,
    load_yaml_file,
    load_yaml_list,
    clean_llm_json_output,
)
from .safety import scan_secrets, detect_license, sanitize_text
from .validator import (
    load_symbols_map, 
    load_symbols_list,
    validate_sample_obj, 
    validate_dataset, 
    validate_file,
)
from .dedup import (
    simhash,
    hamming_distance,
    dedup_jsonl_by_simhash,
    dedup_jsonl_by_semantic,
    calculate_dataset_diversity,
)
from .splitter import group_split_samples, analyze_split_distribution
from .exporter import (
    export_sft_jsonl, 
    export_alpaca_jsonl, 
    export_with_reasoning_trace, 
    export_statistics
)

__all__ = [
    # Schemas
    "Annotation",
    "CodeSymbol",
    "EvidenceRef",
    "ReasoningTrace",
    "TrainingSample",
    "ParsingReport",
    "sha256_text",
    "now_iso",
    # Config
    "Config",
    "config",
    "get_config",
    "reload_config",
    # Logger
    "get_logger",
    "LoggerManager",
    # I/O
    "read_json",
    "write_json",
    "read_jsonl",
    "write_jsonl",
    "append_jsonl",
    "load_prompt_template",
    "load_yaml_file",
    "load_yaml_list",
    "clean_llm_json_output",
    # Safety
    "scan_secrets",
    "detect_license",
    "sanitize_text",
    # Validator
    "load_symbols_map",
    "load_symbols_list",
    "validate_sample_obj",
    "validate_dataset",
    "validate_file",
    # Dedup
    "simhash",
    "hamming_distance",
    "dedup_jsonl_by_simhash",
    "dedup_jsonl_by_semantic",
    "calculate_dataset_diversity",
    # Splitter
    "group_split_samples",
    "analyze_split_distribution",
    # Exporter
    "export_sft_jsonl",
    "export_alpaca_jsonl",
    "export_with_reasoning_trace",
    "export_statistics",
]
