import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from src.schemas import CodeSymbol
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.data.validator import normalize_path_separators
from src.utils.data.sampling import (
    sample_coverage_target, sample_question_type, build_scenario_constraints, build_constraint_rules,
)
from src.utils.io.file_ops import load_yaml_list, append_jsonl
from src.utils.io.loaders import load_symbols_jsonl
from src.utils.generation.config_helpers import parse_coverage_config, create_seeded_rng, resolve_design_limit
from src.engine.core import BaseGenerator

logger = get_logger(__name__)

class DesignQuestionGenerator(BaseGenerator):
    """
    自动设计问题生成器 - 继承自 BaseGenerator
    
    职责：
    1. 自动从代码库中分析并提取具有设计价值的问题。
    2. 支持层级平衡的上下文提取。
    3. 支持批量生成与标准化转换。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """初始化"""
        super().__init__(scenario="arch_design", config=config)
        
        # 1. 核心属性
        self.profile = self._get_language_profile()
        
        # 2. 采样与配置
        self.max_questions = resolve_design_limit(self.config, 50)
        self.top_k_symbols = self.config.get('generation.retrieval_top_k', 6)
        self.coverage_cfg = parse_coverage_config(self.config, 'design_questions')
        self.coverage_rng = create_seeded_rng(self.config)
        
        # 3. 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.design_questions_jsonl',
            'data/intermediate/auto_questions/design_questions_auto.jsonl'
        ))
        
        # 4. 统计
        self.stats = {'total_symbols': 0, 'generated': 0, 'rejected': 0}

    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """从仓库符号生成设计问题"""
        logger.info(f"Generating design questions from {symbols_path}")
        symbols = load_symbols_jsonl(symbols_path)
        if not symbols: return []
        
        if not repo_commit:
            repo_commit = symbols[0].repo_commit
            
        # 1. 过滤候选（主要针对 Controller/Service）
        candidates = [s for s in symbols if s.symbol_type == 'method' and 
                      (self.profile.is_controller(s) or self.profile.is_service(s))]
        
        if not candidates:
            logger.warning("No candidate methods found for design question generation.")
            return []
            
        # Loop until we reach max_questions
        all_normalized_questions = []
        import random
        random.seed(self.config.get('generation.seed', 42))

        while len(all_normalized_questions) < self.max_questions:
            remaining = self.max_questions - len(all_normalized_questions)
            batch_size = min(remaining, 5) # Keep small batch for quality, but accumulate
            
            # 2. 构造 RAG 上下文 (每次循环随机采样不同符号)
            selected_symbols = random.sample(candidates, min(len(candidates), self.top_k_symbols))
            
            context_parts = []
            evidence_pool = []
            for s in selected_symbols:
                context_parts.append(f"// File: {normalize_path_separators(s.file_path)}\n// Method: {s.qualified_name}\n{s.source[:1000]}")
                evidence_pool.append({
                    'symbol_id': normalize_path_separators(s.symbol_id),
                    'file_path': normalize_path_separators(s.file_path),
                    'start_line': s.start_line,
                    'end_line': s.end_line,
                    'source_hash': s.source_hash
                })
                
            context = "\n\n".join(context_parts)
            
            # 3. 采样策略
            coverage_bucket, coverage_intent = sample_coverage_target(self.coverage_cfg, self.coverage_rng)
            question_type = sample_question_type(self.coverage_cfg, self.coverage_rng)
            constraint_strength, constraint_rules = build_constraint_rules(self.coverage_cfg.constraint_strength, coverage_bucket)

            # 4. 组装提示词
            template_name = (
                getattr(self.coverage_cfg, 'template_name', None)
                or self._resolve_template_name(self.config.get("design_questions.prompts.coverage_generation"))
                or self._resolve_template_name(self.config.get("design_questions.prompts.question_generation"))
                or "gen_q_user"
            )
            system_prompt = self._build_composed_system_prompt()
            user_prompt = self._build_composed_user_prompt(
                template_name,
                max_design_questions=batch_size, 
                min_evidence_refs=1,
                context=context,
                evidence_pool=json.dumps(evidence_pool, indent=2, ensure_ascii=False),
                coverage_bucket=coverage_bucket,
                coverage_intent=coverage_intent,
                question_type=question_type,
                scenario_constraints="无",
                constraint_strength=constraint_strength,
                constraint_rules=constraint_rules
            )
            
            # 5. LLM 调用
            try:
                output_dict = self.generate_with_retry(system_prompt, user_prompt)
            except Exception as e:
                logger.error(f"Error during design question batch generation: {e}")
                break

            # 6. 后处理
            questions = output_dict.get("design_questions", [])
            if not questions and "questions" in output_dict:
                questions = output_dict["questions"]
            
            if not questions:
                logger.warning("No questions generated in this batch. Stopping to prevent infinite loop.")
                break

            # 规范化 ID 与关键字段
            self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
            
            batch_added = 0
            for q in questions:
                if len(all_normalized_questions) >= self.max_questions:
                    break

                q['id'] = f"DQ-AUTO-{int(time.time())}-{len(all_normalized_questions)+1}"
                q.setdefault('question_type', question_type)
                # 如果 LLM 没有产出证据，则赋予刚才上下文中的一个
                if not q.get('evidence_refs'):
                    q['evidence_refs'] = [evidence_pool[0]]
                
                all_normalized_questions.append(q)
                append_jsonl(self.output_jsonl, q)
                self.stats['generated'] += 1
                batch_added += 1
            
            logger.info(f"Generated batch of {batch_added} questions. Total: {len(all_normalized_questions)}/{self.max_questions}")
            
            # Prevent infinite loop if we aren't making progress
            if batch_added == 0:
                break
                
        return all_normalized_questions

    def print_summary(self):
        logger.info(f"Design Question Generation Summary: {self.stats['generated']} Generated.")
