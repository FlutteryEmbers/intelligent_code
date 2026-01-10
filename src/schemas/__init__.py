"""
数据模型包 - 分模块定义的 Pydantic 数据结构
"""

from .base import (
    sha256_text,
    now_iso,
    Annotation
)
from .symbols import (
    CodeSymbol,
    EvidenceRef
)
from .samples import (
    ReasoningTrace,
    Quality,
    TrainingSample,
    RejectedSample
)
from .generation import (
    MethodProfile,
    QuestionSample,
    DesignQuestion
)
from .reports import (
    ParsingReport,
    QualityReport
)

__all__ = [
    "sha256_text",
    "now_iso",
    "Annotation",
    "CodeSymbol",
    "EvidenceRef",
    "ReasoningTrace",
    "Quality",
    "TrainingSample",
    "RejectedSample",
    "MethodProfile",
    "QuestionSample",
    "DesignQuestion",
    "ParsingReport",
    "QualityReport"
]
