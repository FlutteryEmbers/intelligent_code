"""
Auto 模块 - 问题生成器

基于 MethodProfile 自动生成多样化的业务问题。
"""
import json
import hashlib
from pathlib import Path
from typing import List

import yaml

from src.utils.schemas import MethodProfile, QuestionSample, CodeSymbol, EvidenceRef
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.validator import normalize_path_separators
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


def load_prompt_template(template_path: str) -> str:
    """加载 prompt 模板文件"""
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


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
        
        # 加载 prompt 模板
        template_path = self.config.get(
            'prompts.question_answer.question_generation',
            'configs/prompts/question_answer/auto_question_generation.txt'
        )
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
        
        # 读取所有 profiles
        profiles = []
        with open(profiles_jsonl, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    profile_dict = json.loads(line)
                    # 转换 evidence_refs
                    evidence_refs = []
                    for ref in profile_dict.get('evidence_refs', []):
                        evidence_refs.append(EvidenceRef(**ref))
                    profile_dict['evidence_refs'] = evidence_refs
                    
                    profiles.append(MethodProfile(**profile_dict))
        
        logger.info(f"Loaded {len(profiles)} profiles")
        self.stats['total_profiles'] = len(profiles)
        
        # 为每个 profile 生成问题
        all_questions = []
        question_hashes = set()  # 用于去重
        
        with open(self.output_jsonl, 'w', encoding='utf-8') as f:
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
                                f.write(q.model_dump_json() + '\n')
                                f.flush()
                                
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
        
        logger.info(f"Question generation completed: {self.stats['total_questions']} questions, {self.stats['duplicates_removed']} duplicates removed")
        return all_questions
    
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
        
        prompt = self.prompt_template.format(
            method_profile=method_profile_json,
            source_code=source_code,
            questions_per_method=self.questions_per_method,
            symbol_id=symbol_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            source_hash=source_hash,
            repo_commit=profile.repo_commit
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
            cleaned_output = self._clean_json_output(raw_output)
            
            # 解析为字典
            result = json.loads(cleaned_output)
            
            # 提取 questions 数组
            questions_data = result.get('questions', [])
            if len(questions_data) != self.questions_per_method:
                logger.warning(f"Expected {self.questions_per_method} questions, got {len(questions_data)}")
            
            # 转换为 QuestionSample
            questions = []
            for q_data in questions_data:
                # 转换 evidence_refs
                evidence_refs = []
                for ref in q_data.get('evidence_refs', []):
                    evidence_refs.append(EvidenceRef(**ref))
                q_data['evidence_refs'] = evidence_refs
                
                # 确保 repo_commit 存在
                if 'repo_commit' not in q_data:
                    q_data['repo_commit'] = profile.repo_commit
                
                question = QuestionSample(**q_data)
                questions.append(question)
            
            return questions
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return []
    
    def _clean_json_output(self, output: str) -> str:
        """清理 LLM 输出，提取纯 JSON"""
        output = output.strip()
        
        # 移除 Markdown 代码块标记
        if output.startswith("```json"):
            output = output[7:]
        elif output.startswith("```"):
            output = output[3:]
        
        if output.endswith("```"):
            output = output[:-3]
        
        output = output.strip()
        
        # 查找第一个 { 和最后一个 }
        start_idx = output.find("{")
        end_idx = output.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            output = output[start_idx:end_idx+1]
        
        return output
    
    def print_summary(self):
        """打印统计摘要"""
        logger.info("=" * 60)
        logger.info("Question Generation Summary")
        logger.info("=" * 60)
        logger.info(f"Total Profiles: {self.stats['total_profiles']}")
        logger.info(f"Total Questions: {self.stats['total_questions']}")
        logger.info(f"Duplicates Removed: {self.stats['duplicates_removed']}")
        logger.info(f"Output: {self.output_jsonl}")
