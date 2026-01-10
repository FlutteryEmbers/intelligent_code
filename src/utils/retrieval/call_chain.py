"""
Weak call-chain expansion for demo usage.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from src.schemas import CodeSymbol

_CALL_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_STOPWORDS = {
    "if", "for", "while", "switch", "catch", "return", "new",
    "try", "throw", "case", "else", "do", "this", "super",
}


def _extract_call_names(source: str) -> set[str]:
    if not source:
        return set()
    names = {match.group(1) for match in _CALL_NAME_RE.finditer(source)}
    return {name for name in names if name not in _STOPWORDS}


def _build_name_index(symbols: Iterable[CodeSymbol]) -> dict[str, list[CodeSymbol]]:
    index: dict[str, list[CodeSymbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol.symbol_type != "method":
            continue
        index[symbol.name].append(symbol)
    return index


def expand_call_chain(
    seeds: list[CodeSymbol],
    symbols: Iterable[CodeSymbol],
    max_depth: int = 1,
    max_expansion: int = 20,
) -> list[CodeSymbol]:
    """Expand call chain from seed symbols.
    
    Args:
        seeds: Starting symbols
        symbols: All available symbols to search
        max_depth: Maximum depth of call chain expansion
        max_expansion: Maximum number of symbols to return
        
    Returns:
        List of expanded CodeSymbol objects
    """
    if max_depth <= 0 or max_expansion <= 0:
        return []
    index = _build_name_index(symbols)
    visited = {symbol.symbol_id for symbol in seeds}
    expansion: list[CodeSymbol] = []

    queue: list[tuple[CodeSymbol, int]] = [(symbol, 0) for symbol in seeds]
    while queue and len(expansion) < max_expansion:
        symbol, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        for name in _extract_call_names(symbol.source):
            for candidate in index.get(name, []):
                if candidate.symbol_id in visited:
                    continue
                visited.add(candidate.symbol_id)
                expansion.append(candidate)
                if len(expansion) >= max_expansion:
                    break
                queue.append((candidate, depth + 1))
            if len(expansion) >= max_expansion:
                break
    return expansion
