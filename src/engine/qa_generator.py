"""
场景 1：QA 数据生成器 - 基于业务规则和流程生成问答对

从解析的代码符号中提取业务规则，生成结构化的问答训练数据。
"""
import json
import time
from pathlib import Path
from typing import Generator
from collections import Counter

from src.utils.schemas import CodeSymbol, TrainingSample, ReasoningTrace, EvidenceRef, sha256_text
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.language_profile import load_language_profile
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


def load_prompt_template(template_name: str) -> str:
    """加载prompt模板文件
    
    Args:
        template_name: 模板文件名（不含路径）
        
    Returns:
        str: 模板内容
    """
    template_path = Path(__file__).parent.parent.parent / "configs" / "prompts" / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


class QAGenerator:
    """
    问答对生成器
    
    从代码符号生成业务规则相关的问答训练数据：
    1. 选择候选符号（优先业务逻辑方法）
    2. 构造上下文（控制长度）
    3. 调用 LLM 生成结构化问答
    4. 校验质量并保存
    
    Note: Rules are now loaded from language profile (configs/language/*.yaml)
    """
    
    def __init__(self, config: Config | None = None):
        """初始化生成器"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # Load language profile for rules
        self.profile = load_language_profile(config=self.config)
        logger.info(f"Loaded language profile: {self.profile.language}")
        
        # 加载prompt模板
        self.system_prompt_template = load_prompt_template("qa_system_prompt.txt")
        self.user_prompt_template = load_prompt_template("qa_user_prompt.txt")
        
        # 从配置读取参数
        self.max_context_chars = self.config.get('qa_generator.max_context_chars', 16000)
        self.batch_size = self.config.get('qa_generator.batch_size', 10)
        self.max_samples = self.config.get('qa_generator.max_samples', 100)
        
        # 输出路径
        self.output_dir = Path('data/intermediate')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.raw_output_path = self.output_dir / 'qa_raw.jsonl'
        self.rejected_path = self.output_dir / 'qa_rejected.jsonl'
        
        # 统计
        self.stats = {
            'total_symbols': 0,
            'selected_symbols': 0,
            'generated_samples': 0,
            'rejected_samples': 0,
            'validation_errors': []
        }
        
        logger.info(f"QAGenerator initialized with max_context_chars={self.max_context_chars}")
    
    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: str | None = None
    ) -> list[TrainingSample]:
        """
        从符号文件生成问答训练数据
        
        Args:
            symbols_path: 符号 JSONL 文件路径
            repo_commit: 仓库 commit（用于校验）
            
        Returns:
            list[TrainingSample]: 生成的训练样本列表
        """
        start_time = time.time()
        logger.info(f"Starting QA generation from {symbols_path}")
        
        # 加载符号
        symbols = self._load_symbols(symbols_path)
        self.stats['total_symbols'] = len(symbols)
        
        if not symbols:
            logger.warning("No symbols loaded")
            return []
        
        # 推断 repo_commit（如果未提供）
        if not repo_commit:
            repo_commit = symbols[0].repo_commit
            logger.info(f"Using repo_commit from symbols: {repo_commit}")
        
        # 选择候选符号
        candidates = self._select_candidates(symbols)
        self.stats['selected_symbols'] = len(candidates)
        
        logger.info(f"Selected {len(candidates)} candidates from {len(symbols)} symbols")
        
        if not candidates:
            logger.warning("No candidates selected")
            return []
        
        # 限制最大生成数量
        if len(candidates) > self.max_samples:
            logger.info(f"Limiting candidates to {self.max_samples} (from {len(candidates)})")
            candidates = candidates[:self.max_samples]
        
        # 批量生成
        samples = []
        for i in range(0, len(candidates), self.batch_size):
            batch = candidates[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (len(candidates) + self.batch_size - 1) // self.batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} symbols)")
            
            batch_samples = self._generate_batch(batch, repo_commit, symbols)
            samples.extend(batch_samples)
            
            logger.info(f"Batch {batch_num}: generated {len(batch_samples)} samples")
        
        # 保存结果
        self._save_samples(samples)
        
        elapsed = time.time() - start_time
        logger.info(f"QA generation completed in {elapsed:.1f}s:")
        logger.info(f"  - Total symbols: {self.stats['total_symbols']}")
        logger.info(f"  - Selected candidates: {self.stats['selected_symbols']}")
        logger.info(f"  - Generated samples: {self.stats['generated_samples']}")
        logger.info(f"  - Rejected samples: {self.stats['rejected_samples']}")
        
        return samples
    
    def _load_symbols(self, symbols_path: Path | str) -> list[CodeSymbol]:
        """加载符号文件"""
        symbols_path = Path(symbols_path)
        
        if not symbols_path.exists():
            raise FileNotFoundError(f"Symbols file not found: {symbols_path}")
        
        symbols = []
        with open(symbols_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    symbol = CodeSymbol(**data)
                    symbols.append(symbol)
                except Exception as e:
                    logger.warning(f"Failed to parse symbol at line {line_num}: {e}")
        
        logger.info(f"Loaded {len(symbols)} symbols from {symbols_path}")
        return symbols
    
    def _select_candidates(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """
        选择候选符号
        
        优先级：
        1. 方法有业务注解/装饰器（基于language profile配置）
        2. 类有业务注解/装饰器
        3. 有文档字符串的方法
        """
        candidates = []
        
        for symbol in symbols:
            if symbol.symbol_type != 'method':
                continue
            
            score = self._calculate_priority_score(symbol)
            
            if score > 0:
                candidates.append(symbol)
        
        # 按优先级排序（分数高的在前）
        candidates.sort(key=lambda s: self._calculate_priority_score(s), reverse=True)
        
        # Record statistics
        if candidates:
            ann_counter = Counter()
            markers = self.profile.get_qa_markers()
            profile_markers = set(markers.get('annotations', [])) | set(markers.get('decorators', []))
            
            for c in candidates:
                for ann in c.annotations:
                    if ann.name in profile_markers:
                        ann_counter[ann.name] += 1
            
            logger.info(f"Candidate marker distribution: {dict(ann_counter.most_common(5))}")
        
        return candidates
    
    def _calculate_priority_score(self, symbol: CodeSymbol) -> int:
        """Calculate priority score based on language profile rules"""
        score = 0
        
        # Get rules from profile
        markers = self.profile.get_qa_markers()
        scoring = self.profile.get_qa_scoring()
        
        # Check annotations/decorators (both stored in symbol.annotations)
        symbol_annotations = {ann.name for ann in symbol.annotations}
        profile_annotations = set(markers.get('annotations', []))
        profile_decorators = set(markers.get('decorators', []))
        
        # Match annotations (Java)
        if symbol_annotations & profile_annotations:
            score += scoring.get('annotation_weight', 10)
        
        # Match decorators (Python, stored as annotations)
        if symbol_annotations & profile_decorators:
            score += scoring.get('decorator_weight', 10)
        
        # Check name keywords
        name_keywords = markers.get('name_keywords', [])
        name_lower = symbol.name.lower()
        qualified_lower = symbol.qualified_name.lower()
        if any(kw in name_lower or kw in qualified_lower for kw in name_keywords):
            score += scoring.get('name_keyword_weight', 1)
        
        # Check path keywords
        path_keywords = markers.get('path_keywords', [])
        path_lower = symbol.file_path.lower()
        if any(kw in path_lower for kw in path_keywords):
            score += scoring.get('name_keyword_weight', 1)
        
        # Has documentation
        if symbol.doc:
            score += scoring.get('doc_weight', 5)
            score += 2
        
        # 方法名暗示业务逻辑
        method_name = symbol.name.lower()
        business_keywords = ['create', 'update', 'delete', 'save', 'process', 'handle', 'execute', 'validate']
        if any(kw in method_name for kw in business_keywords):
            score += 1
        
        return score
    
    def _generate_batch(
        self,
        batch: list[CodeSymbol],
        repo_commit: str,
        all_symbols: list[CodeSymbol]
    ) -> list[TrainingSample]:
        """批量生成训练样本"""
        samples = []
        
        # 创建符号索引（用于校验）
        symbol_index = {s.symbol_id: s for s in all_symbols}
        
        for symbol in batch:
            try:
                sample = self._generate_single(symbol, repo_commit, symbol_index)
                if sample:
                    samples.append(sample)
                    self.stats['generated_samples'] += 1
            except Exception as e:
                logger.error(f"Failed to generate sample for {symbol.symbol_id}: {e}")
                self._log_rejected(symbol, str(e), None)
                self.stats['rejected_samples'] += 1
        
        return samples
    
    def _generate_single(
        self,
        symbol: CodeSymbol,
        repo_commit: str,
        symbol_index: dict[str, CodeSymbol]
    ) -> TrainingSample | None:
        """生成单个训练样本"""
        # 构造上下文（完整信息描述）
        context_desc = self._build_context(symbol)
        
        # 构造 context 字段（源码本身）
        context_code = symbol.source
        
        # 构造 system prompt
        system_prompt = self._build_system_prompt()
        
        # 构造 user prompt（传递完整描述）
        user_prompt = self._build_user_prompt(symbol, context_desc, context_code, repo_commit)
        
        # 调用 LLM
        try:
            sample = self.llm_client.generate_training_sample(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                scenario="qa_rule",
                repo_commit=repo_commit
            )
        except Exception as e:
            logger.warning(f"LLM generation failed for {symbol.symbol_id}: {e}")
            self._log_rejected(symbol, f"LLM error: {e}", None)
            return None
        
        # 强制设置必填字段（防止 LLM 遗漏）
        sample.scenario = "qa_rule"
        sample.repo_commit = repo_commit
        
        # 校验样本
        is_valid, errors = self._validate_sample(sample, symbol, repo_commit, symbol_index)
        
        if not is_valid:
            logger.warning(f"Validation failed for {symbol.symbol_id}: {errors}")
            self._log_rejected(symbol, "Validation failed", {"errors": errors, "sample": sample.model_dump()})
            self.stats['validation_errors'].append({
                'symbol_id': symbol.symbol_id,
                'errors': errors
            })
            return None
        
        # 添加质量标记
        sample.quality = {
            "schema_ok": True,
            "evidence_ok": True,
            "source_symbol": symbol.symbol_id
        }
        
        return sample
    
    def _build_context(self, symbol: CodeSymbol) -> str:
        """
        构造上下文字符串
        
        包含：qualified_name、file_path、annotations、doc、source
        """
        parts = []
        
        # 基本信息
        parts.append(f"方法完全限定名: {symbol.qualified_name}")
        parts.append(f"文件路径: {symbol.file_path}")
        parts.append(f"位置: 第 {symbol.start_line}-{symbol.end_line} 行")
        
        # 注解
        if symbol.annotations:
            parts.append("\n注解:")
            for ann in symbol.annotations:
                if ann.arguments:
                    parts.append(f"  {ann.raw_text}")
                else:
                    parts.append(f"  @{ann.name}")
        
        # Documentation
        if symbol.doc:
            parts.append(f"\n文档说明:\n{symbol.doc}")
        
        # Source code (use language from profile)
        language_name = self.profile.get('language', 'java')
        parts.append(f"\n方法源码:\n```{language_name}\n{symbol.source}\n```")
        
        context = "\n".join(parts)
        
        # 控制长度
        if len(context) > self.max_context_chars:
            # 截断源码部分
            overhead = len(context) - self.max_context_chars
            truncated_source = symbol.source[:len(symbol.source) - overhead - 100]
            truncated_source += "\n\n// ... (源码已截断)"
            
            # 重新构造
            language_name = self.profile.get('language', 'java')
            parts[-1] = f"\n方法源码:\n```{language_name}\n{truncated_source}\n```"
            context = "\n".join(parts)
        
        return context
    
    def _build_system_prompt(self) -> str:
        """构造 system prompt"""
        return self.system_prompt_template
    
    def _build_user_prompt(self, symbol: CodeSymbol, context_desc: str, context_code: str, repo_commit: str) -> str:
        """构造 user prompt"""
        # 提取关键注解
        key_annotations = []
        for ann in symbol.annotations:
            if ann.name in self.BUSINESS_ANNOTATIONS:
                key_annotations.append(f"@{ann.name}")
        
        ann_text = "、".join(key_annotations) if key_annotations else "无特殊注解"
        
        # 使用模板并替换变量
        prompt = self.user_prompt_template.format(
            context_desc=context_desc,
            annotations=ann_text,
            symbol_id=symbol.symbol_id,
            file_path=symbol.file_path,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            source_hash=symbol.source_hash,
            repo_commit=repo_commit,
            context_code=context_code
        )
        
        return prompt
    
    def _validate_sample(
        self,
        sample: TrainingSample,
        source_symbol: CodeSymbol,
        repo_commit: str,
        symbol_index: dict[str, CodeSymbol]
    ) -> tuple[bool, list[str]]:
        """
        校验训练样本
        
        Returns:
            (is_valid, errors)
        """
        errors = []
        
        # 1. 检查 repo_commit
        if sample.repo_commit != repo_commit:
            errors.append(f"repo_commit mismatch: {sample.repo_commit} != {repo_commit}")
        
        # 2. 检查 scenario
        if sample.scenario != "qa_rule":
            errors.append(f"scenario should be 'qa_rule', got '{sample.scenario}'")
        
        # 3. 检查 thought 结构
        if not sample.thought:
            errors.append("thought is missing")
        else:
            if not sample.thought.observations:
                errors.append("thought.observations is empty")
            if not sample.thought.inferences:
                errors.append("thought.inferences is empty")
            if not sample.thought.evidence_refs:
                errors.append("thought.evidence_refs is empty (at least 1 required)")
        
        # 4. 检查 evidence_refs
        if sample.thought and sample.thought.evidence_refs:
            for ref in sample.thought.evidence_refs:
                # 检查 symbol_id 是否存在
                if ref.symbol_id not in symbol_index:
                    errors.append(f"evidence_ref symbol_id not found: {ref.symbol_id}")
                else:
                    # 检查 source_hash 是否匹配
                    ref_symbol = symbol_index[ref.symbol_id]
                    if ref.source_hash != ref_symbol.source_hash:
                        errors.append(
                            f"evidence_ref source_hash mismatch for {ref.symbol_id}: "
                            f"{ref.source_hash} != {ref_symbol.source_hash}"
                        )
        
        # 5. 检查 instruction 和 answer 长度
        if len(sample.instruction) < 10:
            errors.append("instruction too short (< 10 chars)")
        if len(sample.answer) < 20:
            errors.append("answer too short (< 20 chars)")
        
        return len(errors) == 0, errors
    
    def _save_samples(self, samples: list[TrainingSample]):
        """保存训练样本"""
        if not samples:
            logger.warning("No samples to save")
            return
        
        with open(self.raw_output_path, 'w', encoding='utf-8') as f:
            for sample in samples:
                f.write(sample.model_dump_json() + '\n')
        
        logger.info(f"Saved {len(samples)} samples to {self.raw_output_path}")
    
    def _log_rejected(self, symbol: CodeSymbol, reason: str, raw_output: dict | None):
        """记录被拒绝的样本"""
        entry = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'symbol_id': symbol.symbol_id,
            'qualified_name': symbol.qualified_name,
            'reason': reason,
            'raw_output': raw_output
        }
        
        try:
            with open(self.rejected_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Failed to log rejected sample: {e}")
    
    def print_summary(self):
        """打印生成摘要"""
        print("\n" + "=" * 70)
        print(" QA 生成摘要")
        print("=" * 70)
        print(f"总符号数: {self.stats['total_symbols']}")
        print(f"候选符号数: {self.stats['selected_symbols']}")
        print(f"成功生成: {self.stats['generated_samples']}")
        print(f"生成失败: {self.stats['rejected_samples']}")
        
        if self.stats['validation_errors']:
            print(f"\n校验错误类型分布:")
            error_types = Counter()
            for err_entry in self.stats['validation_errors']:
                for err in err_entry['errors']:
                    error_types[err.split(':')[0]] += 1
            
            for err_type, count in error_types.most_common():
                print(f"  - {err_type}: {count}")
        
        print(f"\n输出文件:")
        print(f"  - 成功样本: {self.raw_output_path}")
        print(f"  - 失败样本: {self.rejected_path}")
        print("=" * 70)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='场景 1：QA 数据生成器')
    parser.add_argument(
        '--symbols',
        default='data/raw/extracted/symbols.jsonl',
        help='符号文件路径 (default: data/raw/extracted/symbols.jsonl)'
    )
    parser.add_argument(
        '--repo-commit',
        default=None,
        help='仓库 commit hash（可选，默认从符号文件推断）'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='最大生成样本数（可选，默认从配置读取）'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=None,
        help='批处理大小（可选，默认从配置读取）'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = Config()
    
    # 覆盖配置
    if args.max_samples:
        config._config['qa_generator'] = config._config.get('qa_generator', {})
        config._config['qa_generator']['max_samples'] = args.max_samples
    
    if args.batch_size:
        config._config['qa_generator'] = config._config.get('qa_generator', {})
        config._config['qa_generator']['batch_size'] = args.batch_size
    
    # 初始化生成器
    generator = QAGenerator(config=config)
    
    # 生成
    try:
        samples = generator.generate_from_repo(
            symbols_path=args.symbols,
            repo_commit=args.repo_commit
        )
        
        # 打印摘要
        generator.print_summary()
        
        return 0 if samples else 1
        
    except Exception as e:
        logger.error(f"QA generation failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
