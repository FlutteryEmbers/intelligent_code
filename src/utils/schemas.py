"""
数据模型定义 - 基于 Pydantic 的可追溯/可验证数据结构
"""
import hashlib
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, computed_field


def sha256_text(text: str) -> str:
    """计算文本的 SHA256 哈希值"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat()


class Annotation(BaseModel):
    """Java 注解模型"""
    name: str = Field(..., description="注解名称，如 @Override")
    arguments: dict | None = Field(default=None, description="注解参数字典")
    raw_text: str = Field(..., description="注解原始文本")

    class Config:
        frozen = False


class CodeSymbol(BaseModel):
    """代码符号（类/方法/字段/文件）"""
    symbol_id: str = Field(..., description="稳定主键：{file_path}:{qualified_name}:{start_line}")
    symbol_type: Literal["class", "method", "field", "file"] = Field(..., description="符号类型")
    name: str = Field(..., description="符号名称")
    qualified_name: str = Field(..., description="完全限定名")
    file_path: str = Field(..., description="相对文件路径")
    start_line: int = Field(..., ge=1, description="起始行号（1-based）")
    end_line: int = Field(..., ge=1, description="结束行号（1-based）")
    source: str = Field(..., description="源码片段（可截断）")
    doc: str | None = Field(default=None, description="JavaDoc/注释内容")
    annotations: list[Annotation] = Field(default_factory=list, description="注解列表")
    metadata: dict = Field(default_factory=dict, description="额外元数据")
    repo_commit: str = Field(..., description="仓库 commit hash")
    source_hash: str = Field(..., description="source 字段的 SHA256")

    @computed_field
    @property
    def line_count(self) -> int:
        """计算代码行数"""
        return self.end_line - self.start_line + 1

    def validate_hash(self) -> bool:
        """验证 source_hash 是否匹配"""
        return self.source_hash == sha256_text(self.source)

    @staticmethod
    def make_symbol_id(file_path: str, qualified_name: str, start_line: int) -> str:
        """生成标准化的 symbol_id"""
        return f"{file_path}:{qualified_name}:{start_line}"

    class Config:
        frozen = False


class EvidenceRef(BaseModel):
    """证据引用 - 指向具体的代码位置"""
    symbol_id: str = Field(..., description="引用的符号 ID")
    file_path: str = Field(..., description="文件路径")
    start_line: int = Field(..., ge=1, description="起始行号")
    end_line: int = Field(..., ge=1, description="结束行号")
    source_hash: str = Field(..., description="源码哈希，用于验证")

    class Config:
        frozen = False


class ReasoningTrace(BaseModel):
    """推理轨迹 - 结构化的思考过程（非自由文本 CoT）"""
    observations: list[str] = Field(
        default_factory=list, 
        description="观察到的事实列表"
    )
    inferences: list[str] = Field(
        default_factory=list, 
        description="基于观察的推断列表"
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list, 
        description="支持推理的证据引用"
    )
    assumptions: list[str] = Field(
        default_factory=list, 
        description="做出的假设列表"
    )

    def is_empty(self) -> bool:
        """判断推理轨迹是否为空"""
        return (
            not self.observations 
            and not self.inferences 
            and not self.evidence_refs 
            and not self.assumptions
        )

    class Config:
        frozen = False


class TrainingSample(BaseModel):
    """训练样本 - 用于 Qwen2.5 微调"""
    scenario: Literal["qa_rule", "arch_design"] = Field(
        ..., 
        description="场景类型：qa_rule=规则问答，arch_design=架构设计"
    )
    instruction: str = Field(..., description="指令/问题")
    context: str = Field(..., description="上下文信息")
    thought: ReasoningTrace = Field(
        default_factory=ReasoningTrace, 
        description="结构化推理过程"
    )
    answer: str = Field(..., description="答案/输出")
    repo_commit: str = Field(..., description="数据来源的 commit hash")
    quality: dict = Field(
        default_factory=dict, 
        description="质量评估结果（后续填充）"
    )
    
    # 元数据
    created_at: str = Field(default_factory=now_iso, description="创建时间")
    sample_id: str = Field(default="", description="样本唯一标识")

    def __init__(self, **data):
        super().__init__(**data)
        if not self.sample_id:
            # 自动生成 sample_id
            content = f"{self.scenario}:{self.instruction}:{self.context[:100]}"
            self.sample_id = sha256_text(content)[:16]

    class Config:
        frozen = False


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
