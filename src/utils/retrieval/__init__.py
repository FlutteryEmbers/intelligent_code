"""
Retrieval sub-package.
Provides vector indexing and call chain expansion utilities.
"""
from .vector_index import (
    cosine_similarity,
    build_embeddings,
    search,
)
from .call_chain import (
    expand_call_chain,
)

__all__ = [
    "cosine_similarity",
    "build_embeddings",
    "search",
    "expand_call_chain",
]
