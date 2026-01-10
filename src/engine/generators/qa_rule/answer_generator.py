import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.schemas import QuestionSample, TrainingSample, CodeSymbol, EvidenceRef, ReasoningTrace
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.data.sampling import sample_negative_type
from src.utils.generation.config_helpers import (
    parse_coverage_config, parse_constraints_config,
    parse_output_paths, create_seeded_rng, get_with_fallback
)
from src.utils.io.file_ops import (
    write_json, load_yaml_file, read_jsonl, append_jsonl
)
from src.utils.data.validator import normalize_path_separators
from src.engine.core import BaseGenerator
from src.engine.rag import Retriever

logger = get_logger(__name__)

class AnswerGenerator(BaseGenerator):
    """
    答案生成器 - 继承自 BaseGenerator
    
    职责：
    1. 为给定的问题生成高质量的 TrainingSample。
    2. 利用 Retriever 获取相关的代码上下文。
    3. 支持正向样本与负向采样。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """初始化"""
        super().__init__(scenario="qa_rule", config=config)
        
        # 1. 初始化检索器
        self.retriever = Retriever(self.config, self._get_language_profile())
        
        # 2. 解析业务配置
        self.batch_size = self.config.get('question_answer.batch_size', None)
        self.coverage_cfg = parse_coverage_config(self.config, 'question_answer')
        self.constraints_cfg = parse_constraints_config(self.config, 'question_answer')
        self.negative_rng = create_seeded_rng(self.config)
        
        # 3. 输出路径解析
        self.output_paths = parse_output_paths(
            self.config,
            'artifacts.auto_qa_raw_jsonl', 'data/intermediate/auto_qa_raw.jsonl',
            'artifacts.auto_answer_rejected_jsonl', 'data/intermediate/rejected/auto_answer_rejected.jsonl'
        )
        
        # 4. 加载负向采样规则 (yaml)
        negative_rules_path = Path("configs/prompts/qa_rule/negative_rules.yaml")
        self.negative_rules_map = load_yaml_file(str(negative_rules_path)) if negative_rules_path.exists() else {}

        # 5. 统计初始化
        self.stats = {'total_questions': 0, 'success': 0, 'failed': 0}
        self.retrieval_stats = {
            "mode": self.config.get('generation.retrieval_mode', 'hybrid'),
            "negative_samples": 0,
            "positive_samples": 0,
        }

    def generate_from_questions(
        self,
        questions_jsonl: Path,
        symbols_map: Dict[str, CodeSymbol],
        repo_commit: str = "UNKNOWN_COMMIT"
    ) -> List[TrainingSample]:
        """从 JSONL 文件批量生成答案"""
        logger.info(f"Loading questions from {questions_jsonl}")
        
        # 读取问题流
        questions = []
        for q_dict in read_jsonl(str(questions_jsonl)):
            # 兼容性转换 evidence_refs
            if 'evidence_refs' in q_dict:
                q_dict['evidence_refs'] = [EvidenceRef(**ref) for ref in q_dict['evidence_refs']]
            questions.append(QuestionSample(**q_dict))
        
        self.stats['total_questions'] = len(questions)
        logger.info(f"Loaded {len(questions)} questions. Starting generation...")

        samples = []
        self.config.ensure_output_dirs()
        
        with open(self.output_paths.output_jsonl, 'w', encoding='utf-8') as f_out, \
             open(self.output_paths.rejected_jsonl, 'w', encoding='utf-8') as f_rej:
            
            for i, question in enumerate(questions, 1):
                logger.info(f"[{i}/{len(questions)}] Generating answer for: {question.question[:50]}...")
                
                try:
                    # A. 采样极性
                    negative_type = self._sample_negative_type()
                    if negative_type:
                        self.retrieval_stats["negative_samples"] += 1
                    else:
                        self.retrieval_stats["positive_samples"] += 1
                        
                    # B. 单个生成
                    sample = self._generate_answer(question, list(symbols_map.values()), negative_type)
                    
                    # C. 持久化
                    f_out.write(sample.model_dump_json() + '\n')
                    f_out.flush()
                    samples.append(sample)
                    self.stats['success'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed question {question.question_id}: {e}", exc_info=True)
                    f_rej.write(json.dumps({
                        'question_id': question.question_id,
                        'error': str(e),
                        'timestamp': question.created_at
                    }, ensure_ascii=False) + '\n')
                    f_rej.flush()
                    self.stats['failed'] += 1
        
        self._write_retrieval_report()
        return samples

    def _generate_answer(
        self,
        question: QuestionSample,
        all_symbols: List[CodeSymbol],
        negative_type: Optional[str] = None
    ) -> TrainingSample:
        """核心生成逻辑"""
        
        # 1. 检索上下文 (RAG)
        relevant_symbols = []
        
        # A. Direct Hit (优先使用问题自带的证据)
        if question.evidence_refs:
            logger.debug(f"Question has {len(question.evidence_refs)} direct evidence refs. Skipping retrieval.")
            target_ids = {normalize_path_separators(ref.symbol_id) for ref in question.evidence_refs}
            
            # 从 all_symbols 中查找对应的 CodeSymbol 对象
            for s in all_symbols:
                if normalize_path_separators(s.symbol_id) in target_ids:
                    relevant_symbols.append(s)
            
            # 如果没找到任何符号 (e.g. ID mismatch)，回退到 Retrieval
            if not relevant_symbols:
                logger.warning("Direct evidence refs not found in loaded symbols. Falling back to retrieval.")
                relevant_symbols = self.retriever.retrieve_relevant_symbols(
                    query=question.question,
                    symbols=all_symbols
                )
        else:
            # B. Retrieval (User Mode or No Evidence)
            relevant_symbols = self.retriever.retrieve_relevant_symbols(
                query=question.question,
                symbols=all_symbols
            )
        
        # DEBUG: Log profile structure
        try:
            profile = self._get_language_profile()
            logger.info(f"DEBUG: Profile type: {type(profile)}")
            if isinstance(profile, dict):
                logger.info(f"DEBUG: Profile keys: {list(profile.keys())}")
                qa_section = profile.get('qa')
                logger.info(f"DEBUG: 'qa' section type: {type(qa_section)}")
                ag_section = profile.get('answer_generation')
                logger.info(f"DEBUG: 'answer_generation' section type: {type(ag_section)}")
        except Exception as e:
            logger.error(f"DEBUG: Failed to inspect profile: {e}")
        
        context_parts = []
        available_evidence = []
        for s in relevant_symbols:
            context_parts.append(f"// File: {normalize_path_separators(s.file_path)}\n// Method: {s.qualified_name}\n{s.source}")
            available_evidence.append({
                'symbol_id': normalize_path_separators(s.symbol_id),
                'file_path': normalize_path_separators(s.file_path),
                'start_line': s.start_line,
                'end_line': s.end_line,
                'source_hash': s.source_hash
            })
        
        context = "\n\n".join(context_parts)
        
        # 2. 组装提示词
        # 获取场景特定的格式约束
        qa_config = self._get_language_profile().get('qa', {})
        format_constraints = qa_config.get('answer_format_constraints', "明确、客观，必须引用证据。")
        
        system_prompt = self._build_composed_system_prompt()
        user_prompt = self._build_composed_user_prompt(
            "gen_a_user",
            question=question.question,
            context=context,
            available_evidence_refs=json.dumps(available_evidence, indent=2, ensure_ascii=False),
            repo_commit=question.repo_commit,
            format_constraints=format_constraints,
            architecture_constraints=self._format_architecture_constraints(),
            counterexample_guidance=self._format_counterexample_guidance(),
            common_mistakes_examples=self._format_common_mistakes()
        )
        
        # 3. 注入负向规则 (如果是负向样本)
        if negative_type:
            user_prompt = self._inject_negative_rules(user_prompt, negative_type)
            
        logger.info(f"DEBUG: Generated {len(available_evidence)} available evidence items for prompt.")
        # logger.info(f"DEBUG: FULL PROMPT:\n{user_prompt}") # Uncomment for deep debugging

        # 4. LLM 调用
        output_dict = self.generate_with_retry(system_prompt, user_prompt)
        
        # 5. 后处理与转换
        answer = output_dict.get("answer", "")
        if isinstance(answer, dict): # 兼容一些 LLM 喜欢输出为字典的情况
            answer = json.dumps(answer, ensure_ascii=False)
            
        thought_data = output_dict.get("thought", {})
        if not isinstance(thought_data, dict):
            thought_data = {}
        # 确保 evidence_refs 是对象列表，并进行纠错
        raw_refs = thought_data.get("evidence_refs", [])
        logger.info(f"DEBUG: Raw LLM evidence_refs: {raw_refs}")
        
        evidence_refs = self._correct_evidence_refs(raw_refs, relevant_symbols)
        logger.info(f"DEBUG: Corrected evidence_refs: {evidence_refs}")
        
        thought_data["evidence_refs"] = evidence_refs
        
        quality = self._build_quality_metadata(negative_type, question.question_type)
        
        return TrainingSample(
            scenario="qa_rule",
            instruction=question.question,
            context=context,
            thought=ReasoningTrace(**thought_data),
            answer=answer,
            repo_commit=question.repo_commit,
            quality=quality
        )

    def _sample_negative_type(self) -> Optional[str]:
        return sample_negative_type(
            self.coverage_cfg.negative_ratio,
            self.coverage_cfg.negative_types,
            self.negative_rng
        )

    def _inject_negative_rules(self, prompt: str, negative_type: str) -> str:
        rules_data = self.negative_rules_map.get(negative_type, {})
        rules = rules_data.get('rules', [])
        if not rules:
            return prompt
            
        rules_text = "\n".join(f"- {r}" for r in rules)
        negative_instruction = f"\n\n## 负向样本要求 (Type: {negative_type})\n{rules_text}\n"
        
        # 寻找注入点：通常在 "## 输出要求" 之前
        if "## 输出要求" in prompt:
            return prompt.replace("## 输出要求", f"{negative_instruction}\n## 输出要求")
        return prompt + negative_instruction

    def _format_architecture_constraints(self) -> str:
        constraints = self.constraints_cfg.architecture_constraints or []
        return "\n".join(f"- {c}" for c in constraints) if constraints else "无特定架构约束。"

    def _format_counterexample_guidance(self) -> str:
        return "请在回答中包含一个 'Rejected Alternatives' 部分（如果适用）。" if self.constraints_cfg.enable_counterexample else ""

    def _format_common_mistakes(self) -> str:
        try:
            profile_ag = self._get_language_profile().get('answer_generation', {})
            if isinstance(profile_ag, list):
                logger.warning(f"Unexpected type for 'answer_generation': list. Content: {profile_ag}")
                return "无"
            
            mistakes = profile_ag.get('common_mistakes', [])
            if not mistakes:
                return "无"
            
            lines = []
            for m in mistakes:
                if not isinstance(m, dict): continue
                lines.append(f"❌ 错误 ({m.get('type')}): {m.get('description')}")
                lines.append(f"   错误写法: {m.get('wrong', '').strip()}")
                lines.append(f"   正确写法: {m.get('correct', '').strip()}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error formatting common mistakes: {e}")
            return "无"

    def _build_quality_metadata(self, negative_type: Optional[str], question_type: Optional[str]) -> Dict[str, Any]:
        coverage = {"polarity": "negative" if negative_type else "positive"}
        if question_type:
            coverage["question_type"] = question_type
        if negative_type:
            coverage["negative_type"] = negative_type
        return {"coverage": coverage}

    def _correct_evidence_refs(self, raw_refs: List[Any], symbols: List[CodeSymbol]) -> List[EvidenceRef]:
        """Correlate LLM evidence refs with trusted symbols to fix minor hallucinations or re-hydrate from strings"""
        corrected = []
        
        # Pre-process raw_refs to handle None or non-list
        if not raw_refs or not isinstance(raw_refs, list):
            raw_refs = []

        for ref in raw_refs:
            # Handle string input (symbol_id only)
            if isinstance(ref, str):
                ref = {'symbol_id': ref}
                
            if not isinstance(ref, dict): 
                continue
                
            # Try to find exact or fuzzy match in symbols
            ref_id = ref.get('symbol_id', '')
            best_match = None
            
            # 1. Exact match (normalized)
            norm_ref_id = normalize_path_separators(ref_id)
            for s in symbols:
                if normalize_path_separators(s.symbol_id) == norm_ref_id:
                    best_match = s
                    break
            
            # 2. Fuzzy match (ignore line number suffix)
            if not best_match and ':' in ref_id:
                # Remove line number suffix from ref
                ref_prefix = ref_id.rsplit(':', 1)[0]
                norm_prefix = normalize_path_separators(ref_prefix)
                
                for s in symbols:
                    s_norm_id = normalize_path_separators(s.symbol_id)
                    s_prefix = s_norm_id.rsplit(':', 1)[0]
                    if s_prefix == norm_prefix:
                        best_match = s
                        break
            
            # Apply correction if match found
            if best_match:
                ref['symbol_id'] = normalize_path_separators(best_match.symbol_id)
                ref['file_path'] = normalize_path_separators(best_match.file_path)
                ref['start_line'] = best_match.start_line
                ref['end_line'] = best_match.end_line
                ref['source_hash'] = best_match.source_hash
            
            try:
                # Ensure validation passes
                if not best_match and 'file_path' not in ref:
                     logger.warning(f"Dropping invalid ref {ref_id}: missing file_path and no symbol match.")
                     continue
                corrected.append(EvidenceRef(**ref))
            except Exception as e:
                logger.warning(f"Failed to validate corrected ref: {e}. Dropping.")

        # Fallback Logic (Moved to end): 
        # If we ended up with no valid refs, but we only had 1 candidate symbol in context,
        # it is logically safe to assume that single symbol was the evidence used.
        if not corrected and len(symbols) == 1:
            s = symbols[0]
            logger.info(f"DEBUG: No valid refs found from LLM (Raw: {raw_refs}), but only 1 available symbol ({s.symbol_id}). Auto-filling.")
            return [EvidenceRef(
                symbol_id=normalize_path_separators(s.symbol_id),
                file_path=normalize_path_separators(s.file_path),
                start_line=s.start_line,
                end_line=s.end_line,
                source_hash=s.source_hash
            )]
                
        return corrected

    def _write_retrieval_report(self):
        report_path = Path(self.config.get('output.reports_dir', 'data/reports')) / "qa_answer_retrieval_stats.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(str(report_path), self.retrieval_stats)

    def print_summary(self):
        logger.info("=" * 40)
        logger.info(f"Answer Generation Summary: {self.stats['success']} Succeeded, {self.stats['failed']} Failed")
        logger.info("=" * 40)
