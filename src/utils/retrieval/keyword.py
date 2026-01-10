"""
Simple Keyword Search Utility (BM25-lite)
Provides fallback retrieval when vector embeddings are missing.
"""
import re
from typing import List, Optional, Dict
from src.schemas import CodeSymbol

def keyword_search(
    query: str, 
    symbols: List[CodeSymbol], 
    top_k: int = 5,
    language_profile: Optional[Dict] = None
) -> List[CodeSymbol]:
    """
    Perform weighted keyword search on symbols.
    
    Args:
        query: Search query string
        symbols: List of symbols to search
        top_k: Number of results to return
        language_profile: Optional language profile dict to boost specific keywords
        
    Returns:
        List of top-k matching symbols
    """
    if not query or not symbols:
        return []

    # 1. Normalize query tokens
    tokens = set(re.findall(r'\b\w+\b', query.lower()))
    if not tokens:
        return []

    # 2. Get scoring weights from profile or defaults
    weights = {
        'name_match': 10.0,      # Exact token match in symbol name
        'path_match': 5.0,       # Exact token match in file path
        'source_match': 1.0,     # Exact token match in source code
        'annotation_boost': 0.0, # Boost for having relevant annotations
        'keyword_boost': 0.0     # Boost for matching profile keywords
    }
    
    profile_keywords = set()
    if language_profile:
        # Load weights from profile if available
        qa_scoring = language_profile.get('qa', {}).get('scoring', {})
        weights['name_match'] = float(qa_scoring.get('name_keyword_weight', 10.0)) * 2.0 # Boost query match higher than static keywords
        weights['annotation_boost'] = float(qa_scoring.get('annotation_weight', 0.0))
        
        # Load language specific keywords to boost
        qa_markers = language_profile.get('qa', {}).get('markers', {})
        profile_keywords.update(k.lower() for k in qa_markers.get('name_keywords', []))
        profile_keywords.update(k.lower() for k in qa_markers.get('path_keywords', []))

    scored_symbols = []
    
    for symbol in symbols:
        score = 0.0
        
        # Pre-process symbol fields
        s_name = symbol.qualified_name.lower()
        s_path = symbol.file_path.lower()
        s_source = symbol.source.lower() if symbol.source else ""
        
        # A. Query Token Matching
        for token in tokens:
            # Name match (Highest priority)
            if token in s_name:
                score += weights['name_match']
            # Path match
            elif token in s_path:
                score += weights['path_match']
            # Source match
            elif token in s_source:
                score += weights['source_match']
                
        # B. Static Profile Boosting (Language Specific)
        if language_profile:
            # Check for business annotations/decorators in source
            # This is a simple string check, but effective given source code availability
            # In a real parser we'd check symbol.metadata, but here we fallback to source text
            # if metadata isn't fully populated or consistent.
            # Ideally verify against symbol.metadata if available.
            pass # (Simple implementation: relied on query matching mostly for fallback)
            
            # Boost if symbol name contains high-value keywords (e.g. "Controller", "Service")
            # regardless of query, implying importance? 
            # OR only boost if query ALSO contains them?
            # Let's boost if symbol matches high-value profile keywords to prefer "Business Logic"
            for kw in profile_keywords:
                if kw in s_name:
                    score += 1.0 # Small boost for being a "Service" or "Controller" generally

        if score > 0:
            scored_symbols.append((score, symbol))

    # 3. Sort and Return
    scored_symbols.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored_symbols[:top_k]]
