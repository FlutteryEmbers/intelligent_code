import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from src.schemas import CodeSymbol, MethodProfile, EvidenceRef
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.generation.config_helpers import get_with_fallback
from src.utils.io.file_ops import read_jsonl, append_jsonl
from src.utils.io.loaders import load_symbols_jsonl
from src.utils.data.validator import normalize_path_separators
from src.engine.core import BaseGenerator

logger = get_logger(__name__)

class MethodUnderstander(BaseGenerator):
    """
    方法理解器 - 继承自 BaseGenerator
    
    职责：
    1. 为仓库中的每一个候选方法生成深度的 MethodProfile。
    2. 基于业务敏感度对方法进行优先级评分。
    3. 支持断点续传与批量处理。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """初始化"""
        super().__init__(scenario="method_profile", config=config)
        
        # 1. 配置加载
        self.profile = self._get_language_profile()
        self.max_methods = get_with_fallback(self.config, 'method_understanding.max_methods', 'auto.max_methods', 50)
        
        batching_cfg = self.config.get('method_understanding.batching', {})
        self.output_mode = batching_cfg.get('output_mode', 'overwrite')
        self.resume = bool(batching_cfg.get('resume', False))
        
        # 2. 输出路径
        self.output_jsonl = Path(self.config.get('artifacts.method_profiles_jsonl', 'data/intermediate/method_profiles.jsonl'))
        self.rejected_jsonl = Path(self.config.get('artifacts.auto_method_understanding_rejected_jsonl', 'data/intermediate/rejected/auto_method_understanding_rejected.jsonl'))
        
        # 3. 统计
        self.stats = {'success': 0, 'failed': 0}

    def generate_from_symbols(self, symbols_path: Path, repo_commit: str) -> List[MethodProfile]:
        """批量理解流程"""
        logger.info(f"Loading symbols for understanding from {symbols_path}")
        symbols = load_symbols_jsonl(symbols_path)
        if not symbols: return []
        
        # 1. 筛选并评分
        candidates = self._select_candidates(symbols)
        
        # 2. 状态恢复 (Resume)
        processed_ids = self._load_processed_ids() if self.resume else set()
        candidates = [c for c in candidates if c.symbol_id not in processed_ids]
        
        logger.info(f"Processing {len(candidates)} new methods...")
        
        # 3. 处理输出模式
        if self.output_mode == 'overwrite' and not self.resume:
            self.output_jsonl.unlink(missing_ok=True)
            
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        results = []
        
        for i, symbol in enumerate(candidates, 1):
            logger.info(f"[{i}/{len(candidates)}] Understanding: {symbol.qualified_name}")
            
            try:
                profile = self._generate_profile(symbol, repo_commit)
                append_jsonl(self.output_jsonl, json.loads(profile.model_dump_json()))
                results.append(profile)
                self.stats['success'] += 1
            except Exception as e:
                logger.error(f"Failed to understand {symbol.symbol_id}: {e}")
                append_jsonl(self.rejected_jsonl, {'symbol_id': symbol.symbol_id, 'error': str(e)})
                self.stats['failed'] += 1
                
        return results

    def _select_candidates(self, symbols: List[CodeSymbol]) -> List[CodeSymbol]:
        """筛选高价值方法作为理解对象"""
        methods = [s for s in symbols if s.symbol_type == 'method']
        scored = [(self._calculate_priority_score(s), s) for s in methods]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:self.max_methods]]

    def _calculate_priority_score(self, symbol: CodeSymbol) -> int:
        """评分逻辑：业务注解越丰富，优先级越高"""
        score = 0
        qa_markers = self.profile.get_qa_markers() or {}
        markers = set(qa_markers.get('annotations', []) + qa_markers.get('decorators', []))
        
        for ann in symbol.annotations:
            if ann.name in markers: score += 10
            
        if symbol.doc: score += 5
        if 10 <= symbol.line_count <= 100: score += 5
        return score

    def _generate_profile(self, symbol: CodeSymbol, repo_commit: str) -> MethodProfile:
        """调用 LLM 生成深度规格"""
        system_prompt = self._build_composed_system_prompt()
        user_prompt = self._build_composed_user_prompt(
            "user",
            symbol_id=normalize_path_separators(symbol.symbol_id),
            file_path=normalize_path_separators(symbol.file_path),
            qualified_name=symbol.qualified_name,
            annotations=", ".join([f"@{a.name}" for a in symbol.annotations]) or "无",
            javadoc=symbol.doc or "无",
            source_code=symbol.source,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            source_hash=symbol.source_hash,
            repo_commit=repo_commit
        )
        
        output_dict = self.generate_with_retry(system_prompt, user_prompt)
        
        # 转换 evidence_refs
        raw_refs = output_dict.get('evidence_refs', [])
        output_dict['evidence_refs'] = [EvidenceRef(**ref) if isinstance(ref, dict) else ref for ref in raw_refs]
        
        return MethodProfile(**output_dict)

    def _load_processed_ids(self) -> Set[str]:
        if not self.output_jsonl.exists(): return set()
        return {p.get('symbol_id') for p in read_jsonl(self.output_jsonl) if p.get('symbol_id')}

    def print_summary(self):
        logger.info(f"Understanding Summary: {self.stats['success']} Succeeded, {self.stats['failed']} Failed")
