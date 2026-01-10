"""
Auto 模块 - 问题生成器

基于 MethodProfile 自动生成多样化的业务问题。
"""
import json
import hashlib
from pathlib import Path
from typing import List

import yaml

from src.schemas import MethodProfile, QuestionSample, CodeSymbol, EvidenceRef
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.data.validator import normalize_path_separators
from src.utils.data.sampling import (
    sample_coverage_target, sample_question_type, build_scenario_constraints, build_constraint_rules,
)
from src.utils.io.file_ops import load_prompt_template, load_yaml_list, append_jsonl, clean_llm_json_output
from src.utils.io.loaders import load_profiles_jsonl
from src.utils.generation.config_helpers import parse_coverage_config, create_seeded_rng, resolve_prompt_path
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


def simple_hash(text: str) -> str:
    """简单哈希去重"""
    return hashlib.md5(text.lower().encode('utf-8')).hexdigest()[:16]


def load_user_questions_config(
    config_path: str | Path | None = None,
    repo_commit: str = "UNKNOWN_COMMIT"
) -> List[QuestionSample]:
    """从 YAML 读取用户提供的问题列表"""
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "user_questions.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"User questions config not found: {config_path}")
        return []

    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    items = data.get("user_questions", [])
    if not isinstance(items, list):
        logger.warning(f"Invalid user_questions format in {config_path}")
        return []

    questions: List[QuestionSample] = []
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            logger.warning(f"Skipping user question {idx}: invalid entry")
            continue

        question_text = item.get("question") or item.get("text")
        if not question_text or not isinstance(question_text, str):
            logger.warning(f"Skipping user question {idx}: missing question text")
            continue

        question_type = item.get("question_type") or "business_rule"
        difficulty = item.get("difficulty") or "medium"

        evidence_refs: list[EvidenceRef] = []
        raw_refs = item.get("evidence_refs") or []
        if isinstance(raw_refs, dict):
            raw_refs = [raw_refs]
        if isinstance(raw_refs, list):
            for ref in raw_refs:
                if not isinstance(ref, dict):
                    continue
                try:
                    evidence_refs.append(EvidenceRef(**ref))
                except Exception as e:
                    logger.warning(f"Invalid evidence_ref in user question {idx}: {e}")
        else:
            logger.warning(f"Invalid evidence_refs for user question {idx}")

        item_repo_commit = item.get("repo_commit") or repo_commit
        if item_repo_commit == "UNKNOWN_COMMIT" and repo_commit:
            item_repo_commit = repo_commit

        question_data = {
            "question": question_text,
            "question_type": question_type,
            "difficulty": difficulty,
            "evidence_refs": evidence_refs,
            "repo_commit": item_repo_commit,
        }
        if item.get("created_at"):
            question_data["created_at"] = item["created_at"]
        if item.get("question_id"):
            question_data["question_id"] = item["question_id"]

        try:
            questions.append(QuestionSample(**question_data))
        except Exception as e:
            logger.warning(f"Skipping user question {idx}: {e}")

    logger.info(f"Loaded {len(questions)} user questions from {config_path}")
    return questions


class AutoQuestionGenerator:
    """Auto 问题生成器"""
    
    def __init__(self, config: Config | None = None):
        """初始化"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # 从配置读取参数
        self.questions_per_method = self.config.get('question_answer.questions_per_method', 5)
        self.max_questions = self.config.get('question_answer.max_questions', None)
        self.batch_size = self.config.get('question_answer.batch_size', None)
        
        # 解析覆盖率配置
        self.coverage_cfg = parse_coverage_config(self.config, 'question_answer')
        self.coverage_rng = create_seeded_rng(self.config)
        self.scenario_templates = load_yaml_list(
            self.coverage_cfg.templates_path,
            key='templates'
        ) if self.coverage_cfg.templates_path else []
        
        # 加载 prompt 模板
        coverage_prompt = self.config.get('question_answer.prompts.coverage_generation')
        base_prompt = self.config.get(
            'question_answer.prompts.question_generation',
            'configs/prompts/question_answer/auto_question_generation.txt'
        )
        template_path = resolve_prompt_path(coverage_prompt, base_prompt)
        self.prompt_template = load_prompt_template(template_path)
        
        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.questions_jsonl',
            'data/intermediate/auto_questions/questions.jsonl'
        ))
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计
        self.stats = {
            'total_profiles': 0,
            'total_questions': 0,
            'duplicates_removed': 0,
        }

    def generate_from_profiles(
        self,
        profiles_jsonl: Path,
        symbols_map: dict[str, CodeSymbol],
        repo_commit: str = "UNKNOWN_COMMIT"
    ) -> List[QuestionSample]:
        """从 method profiles 生成问题
        
        Args:
            profiles_jsonl: method_profiles.jsonl 文件路径
            symbols_map: symbol_id -> CodeSymbol 映射
            repo_commit: 仓库 commit hash
            
        Returns:
            List[QuestionSample]: 生成的问题列表
        """
        logger.info(f"Loading profiles from {profiles_jsonl}")
        
        # 读取所有 profiles（使用共享工具）
        profiles = load_profiles_jsonl(profiles_jsonl)
        self.stats['total_profiles'] = len(profiles)
        
        # 为每个 profile 生成问题
        all_questions = []
        question_hashes = set()  # 用于去重
        
        # 清空输出文件
        if self.output_jsonl.exists():
            self.output_jsonl.unlink()
        
        batch_size = self.batch_size or len(profiles) or 1
        for batch_start in range(0, len(profiles), batch_size):
            batch = profiles[batch_start:batch_start + batch_size]
            logger.info(
                "Question batch %s-%s/%s",
                batch_start + 1,
                batch_start + len(batch),
                len(profiles),
            )
            for i, profile in enumerate(batch, batch_start + 1):
                if self.max_questions is not None and self.stats['total_questions'] >= self.max_questions:
                    logger.info(
                        "Reached max_questions=%s, stopping question generation",
                        self.max_questions,
                    )
                    break
                logger.info(f"Generating questions for {i}/{len(profiles)}: {profile.qualified_name}")
                
                try:
                    # 获取源码（标准化路径以支持跨平台）
                    normalized_symbol_id = normalize_path_separators(profile.symbol_id)
                    symbol = symbols_map.get(normalized_symbol_id)
                    if not symbol:
                        logger.warning(f"Symbol not found for {profile.symbol_id}")
                        continue
                    
                    # 生成问题
                    questions = self._generate_questions(profile, symbol)
                    
                    # 去重
                    for q in questions:
                        if self.max_questions is not None and self.stats['total_questions'] >= self.max_questions:
                            break
                        q_hash = simple_hash(q.question)
                        if q_hash not in question_hashes:
                            question_hashes.add(q_hash)
                            all_questions.append(q)
                            
                            # 写入文件
                            question_dict = json.loads(q.model_dump_json())
                            append_jsonl(self.output_jsonl, question_dict)
                            
                            self.stats['total_questions'] += 1
                        else:
                            self.stats['duplicates_removed'] += 1
                    
                    if self.max_questions is not None and self.stats['total_questions'] >= self.max_questions:
                        break
                
                except Exception as e:
                    logger.error(f"Failed to generate questions for {profile.symbol_id}: {e}")
                    continue
                
            if self.max_questions is not None and self.stats['total_questions'] >= self.max_questions:
                    break
        
        potential = self.stats['total_profiles'] * self.questions_per_method
        max_cap = self.max_questions or potential
        logger.info(
            f"Question generation completed: {self.stats['total_questions']}/{max_cap} questions "
            f"(potential: {potential} from {self.stats['total_profiles']} profiles × {self.questions_per_method}/profile, "
            f"duplicates removed: {self.stats['duplicates_removed']})"
        )
        return all_questions

    # 采样方法（使用共享工具）
    def _sample_coverage_target(self) -> tuple[str, str]:
        return sample_coverage_target(self.coverage_cfg, self.coverage_rng)

    def _sample_question_type(self) -> str:
        return sample_question_type(self.coverage_cfg, self.coverage_rng)

    def _build_scenario_constraints(self) -> str:
        return build_scenario_constraints(self.coverage_cfg, self.scenario_templates, self.coverage_rng)

    def _build_constraint_rules(self, bucket: str) -> tuple[str, str]:
        return build_constraint_rules(self.coverage_cfg.constraint_strength, bucket)
    
    def _generate_questions(
        self,
        profile: MethodProfile,
        symbol: CodeSymbol
    ) -> List[QuestionSample]:
        """为单个方法生成问题"""
        # 构造 prompt
        method_profile_json = profile.model_dump_json(indent=2)
        source_code = symbol.source
        
        # 获取 evidence_refs 的第一个（通常是方法自身）
        if profile.evidence_refs:
            first_ref = profile.evidence_refs[0]
            symbol_id = first_ref.symbol_id
            file_path = first_ref.file_path
            start_line = first_ref.start_line
            end_line = first_ref.end_line
            source_hash = first_ref.source_hash
        else:
            # fallback
            symbol_id = profile.symbol_id
            file_path = profile.file_path
            start_line = symbol.start_line
            end_line = symbol.end_line
            source_hash = symbol.source_hash

        default_ref = EvidenceRef(
            symbol_id=symbol_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            source_hash=source_hash,
        )
        
        coverage_bucket, coverage_intent = self._sample_coverage_target()
        question_type = self._sample_question_type()
        scenario_constraints = self._build_scenario_constraints()
        constraint_strength, constraint_rules = self._build_constraint_rules(coverage_bucket)

        prompt = self.prompt_template.format(
            method_profile=method_profile_json,
            source_code=source_code,
            questions_per_method=self.questions_per_method,
            symbol_id=symbol_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            source_hash=source_hash,
            repo_commit=profile.repo_commit,
            coverage_bucket=coverage_bucket,
            coverage_intent=coverage_intent,
            question_type=question_type,
            scenario_constraints=scenario_constraints or "无",
            constraint_strength=constraint_strength,
            constraint_rules=constraint_rules,
        )
        
        # 调用 LLM
        system_prompt = "你是一位资深的业务分析师和技术培训专家，擅长设计高质量的学习问题。"
        
        try:
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
            result = json.loads(cleaned_output)
            
            # 提取 questions 数组
            questions_data = result.get('questions', [])
            if len(questions_data) != self.questions_per_method:
                logger.warning(
                    "Expected %s questions, got %s (symbol=%s)",
                    self.questions_per_method,
                    len(questions_data),
                    symbol.symbol_id,
                )
            if not questions_data:
                logger.warning("No questions returned by LLM for %s", symbol.symbol_id)
            
            # 转换为 QuestionSample
            questions = []
            for q_data in questions_data:
                if 'question_type' not in q_data or not q_data.get('question_type'):
                    q_data['question_type'] = question_type
                # 强制使用已知的证据引用，避免 LLM 产出无效 symbol_id。
                q_data['evidence_refs'] = [default_ref]
                
                # 确保 repo_commit 存在
                if 'repo_commit' not in q_data:
                    q_data['repo_commit'] = profile.repo_commit
                
                question = QuestionSample(**q_data)
                questions.append(question)
            
            return questions
            
        except Exception as e:
            logger.error("LLM call failed for %s: %s", symbol.symbol_id, e)
            return []
    
    def print_summary(self):
        """打印统计摘要"""
        potential = self.stats['total_profiles'] * self.questions_per_method
        max_cap = self.max_questions or potential
        logger.info("=" * 60)
        logger.info("Question Generation Summary")
        logger.info("=" * 60)
        logger.info(f"Total Profiles: {self.stats['total_profiles']}")
        logger.info(f"Questions per Profile: {self.questions_per_method}")
        logger.info(f"Potential Questions: {potential}")
        logger.info(f"Max Questions Cap: {max_cap}")
        logger.info(f"Generated Questions: {self.stats['total_questions']}/{max_cap}")
        logger.info(f"Duplicates Removed: {self.stats['duplicates_removed']}")
        logger.info(f"Output: {self.output_jsonl}")
