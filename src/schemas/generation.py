from typing import Literal
from pydantic import BaseModel, Field
from .base import sha256_text, now_iso
from .symbols import EvidenceRef

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
