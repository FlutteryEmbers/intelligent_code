from typing import Literal
from pydantic import BaseModel, Field
from .base import sha256_text, now_iso
from .symbols import EvidenceRef

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
        description="质量评估结果（结构参考 Quality 模型）"
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

class RejectedSample(BaseModel):
    """被淘汰样本包装器 (写入 rejected/*.jsonl)"""
    line: int = Field(..., description="原始行号")
    scenario: str | None = Field(default=None, description="场景类型")
    error: str | None = Field(default=None, description="错误摘要")
    quality: Quality | None = Field(default=None, description="质量详情")
    raw: dict = Field(default_factory=dict, description="原始样本数据")

    class Config:
        frozen = False
