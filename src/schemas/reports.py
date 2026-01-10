from pydantic import BaseModel, Field
from .base import now_iso

class ParsingReport(BaseModel):
    """解析报告 - 记录解析过程的统计信息"""
    repo_path: str
    repo_commit: str
    total_files: int = 0
    parsed_files: int = 0
    failed_files: int = 0
    total_symbols: int = 0
    symbols_by_type: dict[str, int] = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    parsing_time_seconds: float = 0.0
    created_at: str = Field(default_factory=now_iso)

    class Config:
        frozen = False

class QualityReport(BaseModel):
    """校验报告 (写入 *_validation_report.json)"""
    input_file: str
    symbols_count: int
    gate_version: str
    validation_stats: dict = Field(..., description="{total, passed, failed, pass_rate}")
    top_failures: list[dict]
    top_warnings: list[dict]
    trace_summary: dict
    output_files: dict

    class Config:
        frozen = False
