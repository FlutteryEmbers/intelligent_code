"""
生成引擎模块 - 训练样本生成逻辑

核心组件：
- core: 基础生成器与 LLM 客户端
- rag: 检索增强逻辑
- generators: 业务场景生成器 (QA, Design, Method Profile)
"""

from .core import LLMClient, BaseGenerator
from .rag import Retriever

__all__ = [
    "LLMClient",
    "BaseGenerator",
    "Retriever",
]
