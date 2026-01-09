"""
Auto 模块 - 方法级理解生成器

为候选方法生成深度理解的 MethodProfile。
"""
import json
import time
from pathlib import Path
from typing import Generator

from src.utils.schemas import CodeSymbol, MethodProfile, EvidenceRef, sha256_text
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.language_profile import load_language_profile
from src.utils import load_prompt_template, read_jsonl, append_jsonl, clean_llm_json_output
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


class AutoMethodUnderstander:
    """Auto 方法理解器 - 生成 MethodProfile"""
    
    def __init__(self, config: Config | None = None):
        """初始化"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # Load language profile for business annotations/decorators
        self.profile = load_language_profile(config=self.config)
        logger.info(f"Loaded language profile: {self.profile.language}")
        
        # 从配置读取参数
        self.max_methods = self.config.get(
            'method_understanding.max_methods',
            self.config.get('auto.max_methods', 50),
        )
        self.max_context_chars = self.config.get(
            'core.max_context_chars',
            self.config.get('generation.max_context_chars', 16000),
        )

        batching_cfg = self.config.get('method_understanding.batching', {})
        self.batching_enabled = bool(batching_cfg.get('enabled', False))
        batch_size = batching_cfg.get('batch_size', None)
        self.batch_size = int(batch_size) if batch_size else None
        if self.batch_size is not None and self.batch_size <= 0:
            self.batch_size = None
        self.output_mode = batching_cfg.get('output_mode', 'overwrite')
        if self.output_mode not in ('overwrite', 'append'):
            logger.warning(
                "Unknown output_mode '%s' for method_understanding; falling back to overwrite",
                self.output_mode,
            )
            self.output_mode = 'overwrite'
        self.resume = bool(batching_cfg.get('resume', False))
        
        # 加载 prompt 模板
        template_path = self.config.get(
            'method_understanding.prompts.generation',
            'configs/prompts/method_understanding/auto_method_understanding.txt'
        )
        self.prompt_template = load_prompt_template(template_path)
        
        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.method_profiles_jsonl',
            'data/intermediate/method_profiles.jsonl'
        ))
        self.rejected_jsonl = Path(self.config.get(
            'artifacts.auto_method_understanding_rejected_jsonl',
            'data/intermediate/rejected/auto_method_understanding_rejected.jsonl'
        ))
        
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_jsonl.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计
        self.stats = {
            'total_processed': 0,
            'success': 0,
            'failed': 0,
        }

    def _load_processed_ids(self) -> set[str]:
        """加载已处理的 symbol_id 集合"""
        if not self.output_jsonl.exists():
            return set()
        
        processed = set()
        profiles = read_jsonl(self.output_jsonl)
        for profile in profiles:
            if symbol_id := profile.get('symbol_id'):
                processed.add(symbol_id)
        return processed
    
    def generate_from_symbols(
        self,
        symbols_path: Path,
        repo_commit: str
    ) -> list[MethodProfile]:
        """从 symbols.jsonl 生成 method profiles
        
        Args:
            symbols_path: symbols.jsonl 文件路径
            repo_commit: 仓库 commit hash
            
        Returns:
            list[MethodProfile]: 成功生成的 profiles
        """
        logger.info(f"Loading symbols from {symbols_path}")
        
        # 读取所有符号
        symbol_dicts = read_jsonl(symbols_path)
        symbols = [CodeSymbol(**d) for d in symbol_dicts]
        
        logger.info(f"Loaded {len(symbols)} symbols")
        
        # 选择候选方法
        candidates = self._select_candidates(symbols)
        logger.info(f"Selected {len(candidates)} candidate methods")

        processed_ids: set[str] = set()
        if self.resume:
            if self.output_mode != 'append':
                logger.warning(
                    "resume enabled with output_mode=%s; resume will be ignored",
                    self.output_mode,
                )
                self.resume = False
            else:
                processed_ids = self._load_processed_ids()
                if processed_ids:
                    logger.info("Loaded %s processed method profiles for resume", len(processed_ids))

        if processed_ids:
            before = len(candidates)
            candidates = [c for c in candidates if c.symbol_id not in processed_ids]
            skipped = before - len(candidates)
            if skipped:
                logger.info("Skipped %s already processed methods", skipped)

        # 生成 profiles
        profiles = []
        
        # 如果是 overwrite 模式，先清空文件
        if self.output_mode == 'overwrite':
            if self.output_jsonl.exists():
                self.output_jsonl.unlink()
            if self.rejected_jsonl.exists():
                self.rejected_jsonl.unlink()
        
        total = len(candidates)
        if self.batching_enabled and self.batch_size:
            logger.info(
                "Batching enabled: total=%s, batch_size=%s",
                total,
                self.batch_size,
            )
            batch_ranges = range(0, total, self.batch_size)
        else:
            batch_ranges = [0]

        for batch_start in batch_ranges:
            if self.batching_enabled and self.batch_size:
                batch_end = min(batch_start + self.batch_size, total)
                batch = candidates[batch_start:batch_end]
                logger.info(
                    "Processing batch %s-%s/%s",
                    batch_start + 1,
                    batch_end,
                    total,
                )
            else:
                batch = candidates

            for i, symbol in enumerate(batch, batch_start + 1):
                    logger.info(f"Processing {i}/{total}: {symbol.qualified_name}")

                    try:
                        profile = self._generate_profile(symbol, repo_commit)

                        # 写入成功的 profile
                        profile_dict = json.loads(profile.model_dump_json())
                        append_jsonl(self.output_jsonl, profile_dict)

                        profiles.append(profile)
                        self.stats['success'] += 1

                    except Exception as e:
                        logger.error(f"Failed to generate profile for {symbol.symbol_id}: {e}")

                        # 写入失败记录
                        rejected_entry = {
                            'symbol_id': symbol.symbol_id,
                            'qualified_name': symbol.qualified_name,
                            'error': str(e),
                            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
                        }
                        append_jsonl(self.rejected_jsonl, rejected_entry)

                        self.stats['failed'] += 1

                    self.stats['total_processed'] += 1
        
        logger.info(f"Profile generation completed: {self.stats['success']} success, {self.stats['failed']} failed")
        return profiles
    
    def _select_candidates(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """选择候选方法（复用 QA 选择候选逻辑）"""
        # 只选择方法符号
        methods = [s for s in symbols if s.symbol_type == 'method']
        
        # 计算优先级分数
        scored = []
        for symbol in methods:
            score = self._calculate_priority_score(symbol)
            scored.append((score, symbol))
        
        # 按分数降序排序
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # 取 Top-K
        selected = [s for _, s in scored[:self.max_methods]]
        return selected
    
    def _calculate_priority_score(self, symbol: CodeSymbol) -> int:
        """计算方法的优先级分数"""
        score = 0
        
        # Get business markers from language profile
        qa_markers = self.profile.get_qa_markers()
        business_annotations = set(qa_markers.get('annotations', []))
        business_decorators = set(qa_markers.get('decorators', []))
        
        # 业务注解/装饰器加分
        for ann in symbol.annotations:
            if ann.name in business_annotations or ann.name in business_decorators:
                score += 10
        
        # 有文档加分
        if symbol.doc:
            score += 5
        
        # 代码行数适中加分（太短或太长都不好）
        line_count = symbol.line_count
        if 10 <= line_count <= 100:
            score += 5
        elif 5 <= line_count < 10:
            score += 2
        
        return score
    
    def _generate_profile(
        self,
        symbol: CodeSymbol,
        repo_commit: str
    ) -> MethodProfile:
        """为单个方法生成 profile"""
        # 构造 prompt
        annotations_text = ", ".join([f"@{ann.name}" for ann in symbol.annotations])
        if not annotations_text:
            annotations_text = "无"
        
        javadoc_text = symbol.doc if symbol.doc else "无"
        
        # 截断源码
        source_code = symbol.source
        if len(source_code) > self.max_context_chars:
            source_code = source_code[:self.max_context_chars] + "\n... (源码已截断)"
        
        prompt = self.prompt_template.format(
            symbol_id=symbol.symbol_id,
            file_path=symbol.file_path,
            qualified_name=symbol.qualified_name,
            annotations=annotations_text,
            javadoc=javadoc_text,
            source_code=source_code,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            source_hash=symbol.source_hash,
            repo_commit=repo_commit
        )
        
        # 调用 LLM
        system_prompt = "你是一位资深的 Java 代码分析专家，擅长提取方法的业务语义和架构特征。"
        
        try:
            # 这里直接调用 LLM，期望返回 JSON
            response = self.llm_client.llm.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.llm_client.max_tokens
            )
            
            raw_output = response.content.strip()
            
            # 清理输出
            cleaned_output = clean_llm_json_output(raw_output)
            
            # 解析为字典
            profile_dict = json.loads(cleaned_output)
            
            # 转换 evidence_refs
            evidence_refs = []
            for ref in profile_dict.get('evidence_refs', []):
                evidence_refs.append(EvidenceRef(**ref))
            profile_dict['evidence_refs'] = evidence_refs
            
            # 创建 MethodProfile
            profile = MethodProfile(**profile_dict)
            
            return profile
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def print_summary(self):
        """打印统计摘要"""
        logger.info("=" * 60)
        logger.info("Method Understanding Summary")
        logger.info("=" * 60)
        logger.info(f"Total Processed: {self.stats['total_processed']}")
        logger.info(f"Success: {self.stats['success']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Output: {self.output_jsonl}")
        logger.info(f"Rejected: {self.rejected_jsonl}")
