from typing import Literal
from pydantic import BaseModel, Field, computed_field
from .base import Annotation, sha256_text

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
