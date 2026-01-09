"""
工具模块 - 包含数据模型、配置管理等工具

包结构：
- core/: 核心基础设施 (config, logger, schemas)
- io/: 输入输出操作 (file_ops, loaders, exporters)
- data/: 数据处理与验证 (validator, dedup, splitter, sampling)
- retrieval/: 检索与上下文构建 (vector_index, call_chain)
- generation/: 生成辅助工具 (config_helpers, language_profile)
- safety/: 安全相关 (scanner)

使用方式:
    from src.utils.core.config import Config
    from src.utils.io.file_ops import read_jsonl, write_jsonl
    from src.utils.data.validator import load_symbols_map
    from src.utils.retrieval import vector_index
    from src.utils.generation.config_helpers import parse_coverage_config
    from src.utils.safety.scanner import scan_secrets
"""

__all__ = [
    "core",
    "io", 
    "data",
    "retrieval",
    "generation",
    "safety",
]
