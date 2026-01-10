import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from src.schemas import MethodProfile, QuestionSample, CodeSymbol, EvidenceRef
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.data.validator import normalize_path_separators
from src.utils.data.sampling import (
    sample_coverage_target, sample_question_type, build_scenario_constraints, build_constraint_rules,
)
from src.utils.io.file_ops import load_yaml_list, append_jsonl
from src.utils.io.loaders import load_profiles_jsonl
from src.utils.generation.config_helpers import parse_coverage_config, create_seeded_rng
from src.engine.core import BaseGenerator

logger = get_logger(__name__)

import yaml

def simple_hash(text: str) -> str:
    """简单哈希去重"""
    return hashlib.md5(text.lower().encode('utf-8')).hexdigest()[:16]

def load_user_questions_config(
    config_path: str | Path | None = None,
    repo_commit: str = "UNKNOWN_COMMIT"
) -> List[QuestionSample]:
    """从 YAML 读取用户提供的问题列表"""
    if config_path is None:
        config_path = Path("configs/user_questions.yaml")
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

class QuestionGenerator(BaseGenerator):
    """
    问题生成器 - 继承自 BaseGenerator
    
    职责：
    1. 基于 MethodProfile 自动生成多样化的业务问题。
    2. 支持覆盖率采样与多样性约束。
    3. 支持去重与批量处理。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """初始化"""
        super().__init__(scenario="qa_rule", config=config)
        
        # 1. 业务参数解析
        self.questions_per_method = self.config.get('question_answer.questions_per_method', 5)
        self.max_questions = self.config.get('question_answer.max_questions', None)
        self.batch_size = self.config.get('question_answer.batch_size', None)
        
        # 2. 覆盖率与采样配置
        self.coverage_cfg = parse_coverage_config(self.config, 'question_answer')
        self.coverage_rng = create_seeded_rng(self.config)
        self.scenario_templates = load_yaml_list(
            self.coverage_cfg.templates_path,
            key='templates'
        ) if self.coverage_cfg.templates_path else []
        
        # 3. 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.questions_jsonl',
            'data/intermediate/auto_questions/questions.jsonl'
        ))
        
        # 4. 统计初始化
        self.stats = {
            'total_profiles': 0,
            'total_questions': 0,
            'duplicates_removed': 0,
        }

    def generate_from_profiles(
        self,
        profiles_jsonl: Path,
        symbols_map: Dict[str, CodeSymbol],
        repo_commit: str = "UNKNOWN_COMMIT"
    ) -> List[QuestionSample]:
        """从 method profiles 批量生成问题"""
        logger.info(f"Loading profiles from {profiles_jsonl}")
        
        profiles = load_profiles_jsonl(profiles_jsonl)
        self.stats['total_profiles'] = len(profiles)
        
        all_questions = []
        question_hashes: Set[str] = set()
        
        # 重置输出文件
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        if self.output_jsonl.exists():
            self.output_jsonl.unlink()
            
        profiles_to_process = profiles
        if self.max_questions:
            # 粗略限制处理的 profile 数量以节省时间，但考虑到去重，这里不切片太死
            pass

        for i, profile in enumerate(profiles, 1):
            if self.max_questions and self.stats['total_questions'] >= self.max_questions:
                logger.info(f"Reached max_questions limit ({self.max_questions}). Stopping.")
                break
                
            logger.info(f"[{i}/{len(profiles)}] Generating questions for: {profile.qualified_name}")
            
            try:
                # 获取关联源码
                symbol = symbols_map.get(normalize_path_separators(profile.symbol_id))
                if not symbol:
                    continue
                
                # A. 调用生成
                new_questions = self._generate_questions(profile, symbol)
                
                # B. 去重与过滤
                for q in new_questions:
                    if self.max_questions and self.stats['total_questions'] >= self.max_questions:
                        break
                    
                    q_hash = simple_hash(q.question)
                    if q_hash not in question_hashes:
                        question_hashes.add(q_hash)
                        all_questions.append(q)
                        
                        # C. 实时持久化
                        append_jsonl(self.output_jsonl, json.loads(q.model_dump_json()))
                        self.stats['total_questions'] += 1
                    else:
                        self.stats['duplicates_removed'] += 1
                        
            except Exception as e:
                logger.error(f"Failed to generate questions for {profile.symbol_id}: {e}")
                
        return all_questions

    def _generate_questions(self, profile: MethodProfile, symbol: CodeSymbol) -> List[QuestionSample]:
        """核心生成逻辑"""
        
        # 1. 采样本次生成的策略
        coverage_bucket, coverage_intent = sample_coverage_target(self.coverage_cfg, self.coverage_rng)
        question_type = sample_question_type(self.coverage_cfg, self.coverage_rng)
        scenario_constraints = build_scenario_constraints(self.coverage_cfg, self.scenario_templates, self.coverage_rng)
        constraint_strength, constraint_rules = build_constraint_rules(self.coverage_cfg.constraint_strength, coverage_bucket)
        
        # 2. 准备证据引用基准 (强制 LLM 使用正确的 symbol_id)
        default_ref = EvidenceRef(
            symbol_id=normalize_path_separators(profile.symbol_id),
            file_path=normalize_path_separators(profile.file_path),
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            source_hash=symbol.source_hash
        )
        
        # 3. 组装提示词
        system_prompt = self._build_composed_system_prompt()
        user_prompt = self._build_composed_user_prompt(
            "gen_q_user",
            method_profile=profile.model_dump_json(indent=2),
            source_code=symbol.source,
            questions_per_method=self.questions_per_method,
            symbol_id=normalize_path_separators(profile.symbol_id),
            file_path=normalize_path_separators(profile.file_path),
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            source_hash=symbol.source_hash,
            repo_commit=profile.repo_commit,
            coverage_bucket=coverage_bucket,
            coverage_intent=coverage_intent,
            question_type=question_type,
            scenario_constraints=scenario_constraints or "无",
            constraint_strength=constraint_strength,
            constraint_rules=constraint_rules
        )
        
        # 4. LLM 调用
        output_dict = self.generate_with_retry(system_prompt, user_prompt)
        
        # 5. 结果转换
        questions_data = output_dict.get('questions', [])
        questions = []
        for q_data in questions_data:
            # 补齐关键字段
            q_data.setdefault('question_type', question_type)
            q_data['evidence_refs'] = [default_ref] # 强制覆盖，确保引用有效
            q_data.setdefault('repo_commit', profile.repo_commit)
            
            try:
                questions.append(QuestionSample(**q_data))
            except Exception as e:
                logger.warning(f"Invalid question sample produced by LLM: {e}")
                
        return questions

    def print_summary(self):
        logger.info("=" * 40)
        logger.info(f"Question Generation Summary: {self.stats['total_questions']} Generated, {self.stats['duplicates_removed']} Duplicates Removed")
        logger.info("=" * 40)
