from pathlib import Path
from typing import List, Optional, Tuple, Dict

from src.schemas import CodeSymbol
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.retrieval import vector_index
from src.utils.retrieval.call_chain import expand_call_chain
from src.utils.retrieval.keyword import keyword_search

logger = get_logger(__name__)

class Retriever:
    """
    RAG 检索器 - 统一 向量检索、关键词匹配 与 调用链扩展
    
    该类旨在解耦发电机中的检索逻辑，支持：
    1. 语义检索 (Vector Search)
    2. 基于调用链的上下文扩展 (Call Chain Expansion)
    3. 保证上下文在架构层级上的代表性 (Layer Balancing)
    """
    
    def __init__(self, config: Config, profile):
        """
        初始化检索器
        
        Args:
            config: 全局配置对象
            profile: 语言 Profile 對像 (LanguageProfile)
        """
        self.config = config
        self.profile = profile
        
        # 基础配置
        self.top_k = self.config.get('core.retrieval_top_k', 6)
        self.max_context_chars = self.config.get('core.max_context_chars', 16000)
        
        # 向量索引路径
        self.embeddings_path = Path(self.config.get(
            'artifacts.method_embeddings_jsonl',
            'data/intermediate/method_embeddings.jsonl'
        ))

    def retrieve_relevant_symbols(
        self, 
        query: str, 
        symbols: List[CodeSymbol],
        top_k: Optional[int] = None
    ) -> List[CodeSymbol]:
        """
        检索与查询最相关的符号
        
        Args:
            query: 检索内容 (如问题或需求描述)
            symbols: 全量候选符号列表
            top_k: 覆盖检索数量限制
            
        Returns:
            List[CodeSymbol]: 检索到的相关符号列表
        """
        k = top_k or self.top_k
        logger.debug(f"Retrieving symbols for query: {query[:50]}... (top_k={k})")
        
        # 1. 执行向量语义检索
        retrieved_symbols = []
        if self.embeddings_path.exists():
            scored_ids = vector_index.search(
                query_text=query,
                embeddings_jsonl=self.embeddings_path,
                top_k=k
            )
            
            # Map ID back to CodeSymbol objects
            symbols_map = {s.symbol_id: s for s in symbols}
            for symbol_id, score in scored_ids:
                if symbol_id in symbols_map:
                    retrieved_symbols.append(symbols_map[symbol_id])
                else:
                    logger.warning(f"Retrieved symbol_id {symbol_id} not found in current symbols list")
        else:
            logger.warning(f"Embeddings file missing: {self.embeddings_path}. Falling back to keyword search.")
            # Use Keyword Search (BM25-lite) as fallback
            retrieved_symbols = keyword_search(
                query=query, 
                symbols=symbols, 
                top_k=k,
                language_profile=self.profile.profile_data if hasattr(self.profile, 'profile_data') else None
            )
            
            # Final safety net: if keyword search fails (empty query?), fallback to first k
            if not retrieved_symbols:
                retrieved_symbols = symbols[:k]

        # 2. 调用链扩展 (可选增强)
        if retrieved_symbols and self.config.get('generation.call_chain_enabled', True):
            expanded = expand_call_chain(
                seeds=retrieved_symbols,
                symbols=symbols,
                max_depth=self.config.get('generation.call_chain_max_depth', 1),
                max_expansion=self.config.get('generation.call_chain_max_expansion', 20)
            )
            
            # 合并并去重
            seen_ids = {s.symbol_id for s in retrieved_symbols}
            for s in expanded:
                if s.symbol_id not in seen_ids:
                    retrieved_symbols.append(s)
                    seen_ids.add(s.symbol_id)
        
        # 3. 架构层级平衡
        balanced_symbols = self._balance_layers(retrieved_symbols, symbols, query)
        
        logger.info(f"Retrieved {len(balanced_symbols)} relevant symbols after expansion and balancing")
        return balanced_symbols

    def _balance_layers(
        self, 
        selected: List[CodeSymbol], 
        all_candidates: List[CodeSymbol],
        query: str
    ) -> List[CodeSymbol]:
        """
        保证检索结果中包含 Controller, Service, Repository 等关键层级
        """
        # 统计当前选集中已有的层级
        layers_coverage = {'controller': 0, 'service': 0, 'repository': 0}
        for s in selected:
            layer_type = self.profile.get_layer(s)
            if layer_type in layers_coverage:
                layers_coverage[layer_type] += 1
        
        balanced = list(selected)
        seen_ids = {s.symbol_id for s in balanced}
        
        # 如果某个层级缺失，从全量候选集中寻找该层级的代表
        for layer_name, count in layers_coverage.items():
            if count == 0:
                layer_candidates = self.profile.filter_by_layer(all_candidates, layer_name)
                if layer_candidates:
                    # 使用 Keyword Search 在该层级中找到最相关的一个 (而不是直接取第一个)
                    best_candidates = keyword_search(
                        query=query, 
                        symbols=layer_candidates, 
                        top_k=1,
                        language_profile=self.profile.profile_data if hasattr(self.profile, 'profile_data') else None
                    )
                    
                    candidate = best_candidates[0] if best_candidates else layer_candidates[0]
                    
                    if candidate.symbol_id not in seen_ids:
                        balanced.append(candidate)
                        seen_ids.add(candidate.symbol_id)
                        logger.debug(f"Balanced addition: {candidate.symbol_id} as {layer_name}")
                        
        return balanced
