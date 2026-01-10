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
        description="质量评估结果（结构参考下方 Quality 模型）"
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


# ==================== Demo Module Models ====================

class MethodProfile(BaseModel):
    """方法特征画像 - 用于 demo 模块的方法级理解"""
    symbol_id: str = Field(..., description="符号标识")
    file_path: str = Field(..., description="文件路径")
    qualified_name: str = Field(..., description="完全限定名")
    summary: str = Field(..., description="方法摘要（1-2句话）")
    business_rules: list[str] = Field(default_factory=list, description="业务规则列表")
    inputs: list[dict] = Field(default_factory=list, description="输入参数描述")
    outputs: str = Field(default="", description="返回值描述")
    side_effects: list[str] = Field(default_factory=list, description="副作用列表")
    error_handling: list[str] = Field(default_factory=list, description="错误处理机制")
    consistency: list[str] = Field(default_factory=list, description="一致性保证")
    dependencies: list[str] = Field(default_factory=list, description="依赖列表")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, description="证据引用")
    repo_commit: str = Field(..., description="仓库 commit hash")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    created_at: str = Field(default_factory=now_iso, description="创建时间")

    class Config:
        frozen = False


class QuestionSample(BaseModel):
    """问题样本 - 用于 demo 模块的问题生成"""
    question: str = Field(..., description="问题文本")
    question_type: str = Field(..., description="问题类型")
    difficulty: Literal["easy", "medium", "hard"] = Field(..., description="难度级别")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, description="证据引用")
    repo_commit: str = Field(..., description="仓库 commit hash")
    created_at: str = Field(default_factory=now_iso, description="创建时间")
    question_id: str = Field(default="", description="问题唯一标识")

    def __init__(self, **data):
        super().__init__(**data)
        if not self.question_id:
            # 自动生成 question_id
            content = f"{self.question}:{self.question_type}"
            self.question_id = sha256_text(content)[:16]

    class Config:
        frozen = False


# ==================== Pending / Semi-structured Schemas ====================
# 下列模型已在代码中使用字典形式流转，此处将其结构化定义以供参考或未来重构。

class DesignQuestion(BaseModel):
    """架构设计问题 (原字典结构化)"""
    id: str = Field(..., description="问题 ID (e.g. DQ-AUTO-001)")
    goal: str = Field(..., description="设计目标")
    constraints: list[str] = Field(default_factory=list, description="约束条件")
    acceptance_criteria: list[str] = Field(default_factory=list, description="验收标准")
    non_goals: list[str] = Field(default_factory=list, description="非目标")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, description="相关证据")
    question_type: str = Field(default="architecture", description="问题类型")

    class Config:
        frozen = False


class Quality(BaseModel):
    """质量评估详情 (注入到 TrainingSample.quality)"""
    passed: bool = Field(..., description="是否通过质量门禁")
    gate_version: str = Field(..., description="门禁版本")
    errors: list[dict] = Field(default_factory=list, description="阻断性错误列表")
    warnings: list[dict] = Field(default_factory=list, description="非阻断性警告列表")
    stats: dict = Field(default_factory=dict, description="统计信息 (chars, refs)")
    checks: dict[str, str] = Field(default_factory=dict, description="各维度检查状态 (pass/warn/fail)")

    class Config:
        frozen = False


class RejectedSample(BaseModel):
    """被淘汰样本包装器 (写入 rejected/*.jsonl)"""
    line: int = Field(..., description="原始行号")
    scenario: str | None = Field(default=None, description="场景类型")
    error: str | None = Field(default=None, description="错误摘要")
    quality: Quality | None = Field(default=None, description="质量详情")
    raw: dict = Field(default_factory=dict, description="原始样本数据")

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
