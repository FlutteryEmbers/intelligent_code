"""
场景 2：架构设计方案生成器 - 基于设计问题生成设计方案

从代码仓库中检索相关上下文，为给定设计问题生成架构设计方案。
"""
import json
import random
import time
from pathlib import Path
from typing import Generator
from collections import Counter

import yaml

from src.utils.schemas import CodeSymbol, TrainingSample, ReasoningTrace, EvidenceRef, sha256_text
from src.utils import write_json
from src.utils.call_chain import expand_call_chain
from src.utils.validator import normalize_path_separators
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.language_profile import load_language_profile
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


def load_prompt_template(template_path: str | Path) -> str:
    """加载prompt模板文件
    
    Args:
        template_path: 模板文件路径
        
    Returns:
        str: 模板内容
    """
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()


def load_design_questions_config(config_path: str | Path | None = None) -> list['DesignQuestion']:
    """从 YAML 配置文件加载设计问题定义
    
    Args:
        config_path: 配置文件路径，默认为 configs/design_questions.yaml
        
    Returns:
        list[DesignQuestion]: 设计问题对象列表
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "configs" / "design_questions.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        logger.warning(f"Design questions config not found: {config_path}, using empty list")
        return []
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        design_questions = []
        for question_data in data.get('design_questions', []):
            question = DesignQuestion(
                id=question_data['id'],
                goal=question_data['goal'],
                constraints=question_data.get('constraints', []),
                acceptance_criteria=question_data.get('acceptance_criteria', []),
                non_goals=question_data.get('non_goals', []),
            )
            design_questions.append(question)
        
        logger.info(f"Loaded {len(design_questions)} design questions from {config_path}")
        return design_questions
        
    except Exception as e:
        logger.error(f"Failed to load design questions config: {e}")
        return []


class DesignQuestion:
    """设计问题模型"""
    def __init__(
        self,
        id: str,
        goal: str,
        constraints: list[str],
        acceptance_criteria: list[str],
        non_goals: list[str] | None = None
    ):
        self.id = id
        self.goal = goal
        self.constraints = constraints
        self.acceptance_criteria = acceptance_criteria
        self.non_goals = non_goals or []
    
    def to_dict(self):
        return {
            'id': self.id,
            'goal': self.goal,
            'constraints': self.constraints,
            'acceptance_criteria': self.acceptance_criteria,
            'non_goals': self.non_goals
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DesignQuestion':
        """从字典创建 DesignQuestion 对象"""
        return cls(
            id=data['id'],
            goal=data['goal'],
            constraints=data.get('constraints', []),
            acceptance_criteria=data.get('acceptance_criteria', []),
            non_goals=data.get('non_goals', [])
        )


class DesignGenerator:
    """
    架构设计方案生成器
    
    为给定设计问题生成基于现有代码架构的设计方案：
    1. 设计问题结构化存储
    2. 轻量级 RAG（过滤 + 检索）
    3. LLM 生成设计方案
    4. 质量校验并保存
    
    Note: Layer identification rules now loaded from language profile (configs/language/*.yaml)
    """
    
    def __init__(self, config: Config | None = None):
        """初始化生成器"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # Load language profile for layer identification
        self.profile = load_language_profile(config=self.config)
        logger.info(f"Loaded language profile: {self.profile.language}")
        
        # 加载prompt模板
        system_prompt_path = self.config.get(
            'design_questions.prompts.system_prompt',
            'configs/prompts/design/design_system_prompt.txt',
        )
        user_prompt_path = self.config.get(
            'design_questions.prompts.user_prompt',
            'configs/prompts/design/design_user_prompt.txt',
        )
        self.system_prompt_template = load_prompt_template(system_prompt_path)
        self.user_prompt_template = load_prompt_template(user_prompt_path)
        
        # 从配置读取参数
        self.top_k_context = self.config.get(
            'core.retrieval_top_k',
            self.config.get('generation.retrieval_top_k', 6),
        )
        self.max_context_chars = self.config.get(
            'core.max_context_chars',
            self.config.get('generation.max_context_chars', 16000),
        )
        self.max_samples = self.config.get(
            'core.max_items',
            self.config.get('generation.max_items', 50),
        )
        self.coverage_config = self.config.get('design_questions.coverage', {}) or {}
        self.negative_ratio = self.coverage_config.get('negative_ratio')
        self.negative_types = self.coverage_config.get('negative_types', [])
        if not isinstance(self.negative_types, list):
            self.negative_types = []
        self.negative_rng = random.Random(self.config.get('core.seed', 42))
        self.retrieval_config = self.config.get('design_questions.retrieval', {}) or {}
        self.retrieval_mode = self.retrieval_config.get('mode', 'hybrid')
        self.retrieval_fallback_top_k = int(
            self.retrieval_config.get('fallback_top_k', self.top_k_context)
        )
        call_chain_cfg = self.retrieval_config.get("call_chain", {}) or {}
        self.call_chain_enabled = bool(call_chain_cfg.get("enabled", False))
        self.call_chain_max_depth = int(call_chain_cfg.get("max_depth", 1))
        self.call_chain_max_expansion = int(call_chain_cfg.get("max_expansion", 20))
        self.retrieval_stats = {
            "mode": self.retrieval_mode,
            "fallback_top_k": self.retrieval_fallback_top_k,
            "total_questions": 0,
            "candidates_empty": 0,
            "scored_non_empty": 0,
            "fallback_used": 0,
            "call_chain_expanded": 0,
            "negative_samples": 0,
            "positive_samples": 0,
        }
        
        # 输出路径
        self.output_dir = Path(self.config.get('output.intermediate_dir', 'data/intermediate'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.design_questions_path = Path(self.config.get(
            'artifacts.design_questions_snapshot_jsonl',
            self.output_dir / 'auto_questions' / 'design_questions.jsonl',
        ))
        self.raw_output_path = self.output_dir / 'design_raw.jsonl'
        self.rejected_path = Path(self.config.get(
            'artifacts.design_rejected_jsonl',
            self.output_dir / 'rejected' / 'design_rejected.jsonl',
        ))
        self.design_questions_path.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计
        self.stats = {
            'total_design_questions': 0,
            'generated_samples': 0,
            'rejected_samples': 0,
            'validation_errors': []
        }
        
        logger.info(f"DesignGenerator initialized with top_k={self.top_k_context}, max_context_chars={self.max_context_chars}")
    
    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: str | None = None,
        design_questions: list[DesignQuestion] | None = None
    ) -> list[TrainingSample]:
        """
        从符号文件和设计问题生成设计方案
        
        Args:
            symbols_path: 符号 JSONL 文件路径
            repo_commit: 仓库 commit
            design_questions: 设计问题列表（可选，默认使用内置问题）
            
        Returns:
            list[TrainingSample]: 生成的训练样本列表
        """
        start_time = time.time()
        logger.info(f"Starting design generation from {symbols_path}")
        
        # 加载符号
        symbols = self._load_symbols(symbols_path)
        
        if not symbols:
            logger.warning("No symbols loaded")
            return []
        
        # 推断 repo_commit
        if not repo_commit:
            repo_commit = symbols[0].repo_commit
            logger.info(f"Using repo_commit from symbols: {repo_commit}")
        
        # 使用自定义设计问题或从配置文件加载
        if design_questions is None:
            design_questions = load_design_questions_config()
        
        self.stats['total_design_questions'] = len(design_questions)
        self.retrieval_stats["total_questions"] = len(design_questions)
        
        # 保存设计问题到文件
        self._save_design_questions(design_questions)
        
        # 限制设计问题数量
        if len(design_questions) > self.max_samples:
            logger.info(
                "Limiting design questions to %s (from %s)",
                self.max_samples,
                len(design_questions),
            )
            design_questions = design_questions[:self.max_samples]
        
        # 为每个设计问题生成设计方案
        samples = []
        for i, question in enumerate(design_questions, 1):
            logger.info(
                "Processing design question %s/%s: %s",
                i,
                len(design_questions),
                question.id,
            )
            
            try:
                negative_type = self._sample_negative_type()
                if negative_type:
                    self.retrieval_stats["negative_samples"] += 1
                else:
                    self.retrieval_stats["positive_samples"] += 1
                sample = self._generate_single(question, symbols, repo_commit, negative_type)
                if sample:
                    samples.append(sample)
                    self.stats['generated_samples'] += 1
            except Exception as e:
                logger.error(f"Failed to generate sample for {question.id}: {e}")
                self._log_rejected(question, str(e), None)
                self.stats['rejected_samples'] += 1
        
        # 保存结果
        self._save_samples(samples)
        
        elapsed = time.time() - start_time
        logger.info(f"Design generation completed in {elapsed:.1f}s:")
        logger.info(f"  - Total design questions: {self.stats['total_design_questions']}")
        logger.info(f"  - Generated samples: {self.stats['generated_samples']}")
        logger.info(f"  - Rejected samples: {self.stats['rejected_samples']}")
        
        self._write_retrieval_report()
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
    
    def _save_design_questions(self, design_questions: list[DesignQuestion]):
        """保存设计问题到 JSONL"""
        with open(self.design_questions_path, 'w', encoding='utf-8') as f:
            for question in design_questions:
                f.write(json.dumps(question.to_dict(), ensure_ascii=False) + '\n')
        
        logger.info(f"Saved {len(design_questions)} design questions to {self.design_questions_path}")
    
    def _generate_single(
        self, 
        design_question: DesignQuestion,
        symbols: list[CodeSymbol],
        repo_commit: str,
        negative_type: str | None = None
    ) -> TrainingSample | None:
        """为单个设计问题生成设计方案"""
        # 1. RAG：检索相关上下文
        relevant_symbols = self._retrieve_context(design_question, symbols)
        
        if not relevant_symbols:
            logger.warning(f"No relevant symbols found for {design_question.id}")
            self._log_rejected(design_question, "No relevant context found", None)
            return None
        
        logger.info(f"Retrieved {len(relevant_symbols)} relevant symbols for {design_question.id}")
        
        # 2. 构造上下文
        context = self._build_context(relevant_symbols, design_question)
        
        # 3. 构造 prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(design_question, context, relevant_symbols, repo_commit)
        user_prompt = self._inject_negative_rules(user_prompt, negative_type)
        
        # 4. 调用 LLM（最小结构输出：answer + thought）
        raw_output = ""
        try:
            response = self.llm_client.llm.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.llm_client.max_tokens,
            )
            raw_output = response.content.strip()
            cleaned_output = self._clean_json_output(raw_output)
            minimal_dict = json.loads(cleaned_output)
        except Exception as e:
            logger.warning(f"LLM generation failed for {design_question.id}: {e}")
            self._log_rejected(
                design_question,
                f"LLM error: {e}",
                {"raw_output": raw_output},
            )
            return None

        try:
            answer_value = minimal_dict.get("answer")
            if answer_value is None:
                raise ValueError("LLM output missing 'answer' field")
            if isinstance(answer_value, dict):
                answer_value = json.dumps(answer_value, ensure_ascii=False)
            elif not isinstance(answer_value, str):
                answer_value = str(answer_value)

            thought_dict = minimal_dict.get("thought")
            if not isinstance(thought_dict, dict):
                raise ValueError("LLM output missing 'thought' object")
            for key in ("observations", "inferences", "assumptions"):
                if key not in thought_dict or not isinstance(thought_dict[key], list):
                    thought_dict[key] = []
            raw_refs = thought_dict.get("evidence_refs", [])
            if not isinstance(raw_refs, list) or len(raw_refs) < 2:
                raise ValueError("thought.evidence_refs must have at least 2 items")
            evidence_refs = []
            for ref in raw_refs:
                evidence_refs.append(EvidenceRef(**ref))
            thought_dict["evidence_refs"] = evidence_refs
            reasoning_trace = ReasoningTrace(**thought_dict)
        except Exception as e:
            logger.warning(f"LLM output invalid for {design_question.id}: {e}")
            self._log_rejected(
                design_question,
                f"LLM output invalid: {e}",
                {"raw_output": raw_output},
            )
            return None

        # 5. 构造 TrainingSample（其余字段由系统填充）
        quality = self._build_quality(negative_type, design_question.id, len(relevant_symbols))
        sample = TrainingSample(
            scenario="arch_design",
            instruction=design_question.goal,
            context=context,
            thought=reasoning_trace,
            answer=answer_value,
            repo_commit=repo_commit,
            quality=quality,
        )
        
        # 6. 校验样本
        is_valid, errors = self._validate_sample(sample, design_question, repo_commit, symbols)
        
        if not is_valid:
            logger.warning(f"Validation failed for {design_question.id}: {errors}")
            self._log_rejected(
                design_question,
                "Validation failed",
                {"errors": errors, "sample": sample.model_dump()}
            )
            self.stats['validation_errors'].append({
                'design_question_id': design_question.id,
                'errors': errors
            })
            return None
        
        # 7. 添加质量标记
        return sample
    
    def _retrieve_context(
        self,
        design_question: DesignQuestion,
        symbols: list[CodeSymbol]
    ) -> list[CodeSymbol]:
        """
        轻量级 RAG：两段式检索
        
        1. 过滤：优先 Controller/Service/Repository
        2. 检索：关键词打分，返回 top_k
        """
        # 第一阶段：过滤候选
        candidates = self._filter_candidates(symbols)
        
        if not candidates:
            logger.warning("No candidates after filtering")
            self.retrieval_stats["candidates_empty"] += 1
            return []
        
        logger.debug(f"Filtered to {len(candidates)} candidates")
        
        # 第二阶段：关键词检索打分
        scored_candidates = []
        
        # 提取设计问题关键词
        req_keywords = self._extract_keywords(design_question.goal)
        
        if self.retrieval_mode != "symbol_only":
            for symbol in candidates:
                score = self._calculate_relevance_score(symbol, req_keywords)
                if score > 0:
                    scored_candidates.append((symbol, score))
        
        # 按分数排序
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        if scored_candidates:
            self.retrieval_stats["scored_non_empty"] += 1
            top_symbols = [s for s, _ in scored_candidates[:self.top_k_context]]
        else:
            if self.retrieval_mode == "symbol_only" or self.retrieval_mode == "hybrid":
                self.retrieval_stats["fallback_used"] += 1
                top_symbols = candidates[: self.retrieval_fallback_top_k]
            else:
                top_symbols = []
        
        # 确保包含不同层级
        top_symbols = self._balance_layers(top_symbols, candidates)

        if self.call_chain_enabled and top_symbols:
            expanded = expand_call_chain(
                top_symbols,
                symbols,
                max_depth=self.call_chain_max_depth,
                max_expansion=self.call_chain_max_expansion,
            )
            added = 0
            existing = {symbol.symbol_id for symbol in top_symbols}
            for symbol in expanded:
                if symbol.symbol_id in existing:
                    continue
                top_symbols.append(symbol)
                existing.add(symbol.symbol_id)
                added += 1
                if added >= self.call_chain_max_expansion:
                    break
            self.retrieval_stats["call_chain_expanded"] += added

        return top_symbols
    
    def _filter_candidates(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """Filter candidate symbols (any layer from profile)"""
        candidates = []
        
        for symbol in symbols:
            if symbol.symbol_type != 'method':
                continue
            
            # Check if symbol belongs to any design layer
            if (self._is_controller(symbol) or 
                self._is_service(symbol) or 
                self._is_repository(symbol)):
                candidates.append(symbol)
        
        return candidates
    
    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词（简单版：分词 + 过滤停用词）"""
        # 简单分词
        words = text.lower().split()
        
        # 停用词
        stopwords = {'的', '了', '在', '是', '为', '和', '与', '或', '但', '等', 
                     'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        
        # 过滤
        keywords = [w for w in words if len(w) > 1 and w not in stopwords]
        
        return keywords
    
    def _calculate_relevance_score(self, symbol: CodeSymbol, req_keywords: list[str]) -> int:
        """Calculate relevance score between symbol and design question keywords"""
        score = 0
        
        # Search in qualified_name + doc + source
        search_text = f"{symbol.qualified_name} {symbol.doc or ''} {symbol.source}".lower()
        
        # Keyword matching
        for keyword in req_keywords:
            if keyword in search_text:
                score += 1
        
        # Layer-based scoring
        if self._is_controller(symbol):
            score += 3  # Controllers are entry points
        elif self._is_service(symbol):
            score += 2  # Services are core logic
        elif self._is_repository(symbol):
            score += 1  # Repositories are data access
        
        # Documentation bonus
        if symbol.doc:
            score += 1
        
        return score
    
    def _balance_layers(
        self,
        selected: list[CodeSymbol],
        all_candidates: list[CodeSymbol]
    ) -> list[CodeSymbol]:
        """平衡不同架构层级"""
        # 统计已选择的层级
        layers = {'controller': 0, 'service': 0, 'repository': 0}
        
        for symbol in selected:
            if self._is_controller(symbol):
                layers['controller'] += 1
            elif self._is_service(symbol):
                layers['service'] += 1
            elif self._is_repository(symbol):
                layers['repository'] += 1
        
        # 如果缺少 Controller，尝试补充
        if layers['controller'] == 0:
            for candidate in all_candidates:
                if self._is_controller(candidate) and candidate not in selected:
                    selected.insert(0, candidate)
                    break
        
        # 如果缺少 Service，尝试补充
        if layers['service'] == 0:
            for candidate in all_candidates:
                if self._is_service(candidate) and candidate not in selected:
                    selected.append(candidate)
                    break
        
        return selected
    
    def _is_controller(self, symbol: CodeSymbol) -> bool:
        """Check if symbol is a controller using language profile rules"""
        layer_rules = self.profile.get_design_layer('controller')
        return self._matches_layer_rules(symbol, layer_rules)
    
    def _is_service(self, symbol: CodeSymbol) -> bool:
        """Check if symbol is a service using language profile rules"""
        layer_rules = self.profile.get_design_layer('service')
        return self._matches_layer_rules(symbol, layer_rules)
    
    def _is_repository(self, symbol: CodeSymbol) -> bool:
        """Check if symbol is a repository using language profile rules"""
        layer_rules = self.profile.get_design_layer('repository')
        return self._matches_layer_rules(symbol, layer_rules)
    
    def _matches_layer_rules(self, symbol: CodeSymbol, layer_rules: dict) -> bool:
        """Generic layer matching based on profile rules"""
        # Check annotations/decorators (both in symbol.annotations)
        symbol_annotations = {ann.name for ann in symbol.annotations}
        profile_annotations = set(layer_rules.get('annotations', []))
        profile_decorators = set(layer_rules.get('decorators', []))
        
        if symbol_annotations & (profile_annotations | profile_decorators):
            return True
        
        # Check name keywords
        name_keywords = layer_rules.get('name_keywords', [])
        name_lower = symbol.name.lower()
        qualified_lower = symbol.qualified_name.lower()
        if any(kw in name_lower or kw in qualified_lower for kw in name_keywords):
            return True
        
        # Check path keywords
        path_keywords = layer_rules.get('path_keywords', [])
        path_lower = symbol.file_path.lower()
        if any(kw in path_lower for kw in path_keywords):
            return True
        
        return False
    
    def _build_context(
        self,
        symbols: list[CodeSymbol],
        design_question: DesignQuestion
    ) -> str:
        """构造上下文字符串"""
        parts = []
        
        # 按层级分组
        controllers = [s for s in symbols if self._is_controller(s)]
        services = [s for s in symbols if self._is_service(s)]
        repositories = [s for s in symbols if self._is_repository(s)]
        
        # Controller 层
        if controllers:
            # Get language name from profile
            language_name = self.profile.get('language', 'java')
            
            parts.append("# Controller 层（入口）")
            for symbol in controllers:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.annotations:
                    parts.append(f"注解/装饰器: {', '.join([f'@{a.name}' for a in symbol.annotations])}")
                if symbol.doc:
                    parts.append(f"文档: {symbol.doc[:200]}...")
                parts.append(f"```{language_name}\n{symbol.source[:500]}...\n```")
        
        # Service 层
        if services:
            language_name = self.profile.get('language', 'java')
            parts.append("\n# Service 层（业务逻辑）")
            for symbol in services:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.annotations:
                    parts.append(f"注解/装饰器: {', '.join([f'@{a.name}' for a in symbol.annotations])}")
                if symbol.doc:
                    parts.append(f"文档: {symbol.doc[:200]}...")
                parts.append(f"```{language_name}\n{symbol.source[:500]}...\n```")
        
        # Repository 层
        if repositories:
            language_name = self.profile.get('language', 'java')
            parts.append("\n# Repository 层（数据访问）")
            for symbol in repositories:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.annotations:
                    parts.append(f"注解/装饰器: {', '.join([f'@{a.name}' for a in symbol.annotations])}")
                parts.append(f"```{language_name}\n{symbol.source[:300]}...\n```")
        
        context = "\n".join(parts)
        
        # 控制长度
        if len(context) > self.max_context_chars:
            context = context[:self.max_context_chars] + "\n\n... (上下文已截断)"
        
        return context
    
    def _build_system_prompt(self) -> str:
        """构造 system prompt"""
        return self.system_prompt_template
    
    def _build_user_prompt(
        self,
        design_question: DesignQuestion,
        context: str,
        symbols: list[CodeSymbol],
        repo_commit: str
    ) -> str:
        """构造 user prompt"""
        # 选择关键符号用于示例
        controller_symbol = next((s for s in symbols if self._is_controller(s)), symbols[0])
        service_symbol = next((s for s in symbols if self._is_service(s)), symbols[0] if len(symbols) > 0 else None)
        
        # 准备约束条件、验收标准和非目标的格式化文本
        constraints_text = '\n'.join([f'- {c}' for c in design_question.constraints])
        acceptance_criteria_text = '\n'.join([f'- {a}' for a in design_question.acceptance_criteria])
        non_goals_text = '\n'.join([f'- {n}' for n in design_question.non_goals])
        
        # 统一路径分隔符以避免 JSON 转义问题
        controller_symbol_id = normalize_path_separators(controller_symbol.symbol_id)
        controller_file_path = normalize_path_separators(controller_symbol.file_path)

        service_symbol_id = None
        service_file_path = None
        if service_symbol:
            service_symbol_id = normalize_path_separators(service_symbol.symbol_id)
            service_file_path = normalize_path_separators(service_symbol.file_path)

        # 准备service evidence文本
        if service_symbol:
            service_evidence = f"""
Service 核心逻辑：
- symbol_id: "{service_symbol_id}"
- file_path: "{service_file_path}"
- start_line: {service_symbol.start_line}
- end_line: {service_symbol.end_line}
- source_hash: "{service_symbol.source_hash}"
"""
            service_evidence_json = f""",
      {{
        "symbol_id": "{service_symbol_id}",
        "file_path": "{service_file_path}",
        "start_line": {service_symbol.start_line},
        "end_line": {service_symbol.end_line},
        "source_hash": "{service_symbol.source_hash}"
      }}"""
        else:
            service_evidence = ""
            service_evidence_json = ""
        
        # 使用模板并替换变量
        prompt = self.user_prompt_template.format(
            design_question_id=design_question.id,
            goal=design_question.goal,
            constraints=constraints_text,
            acceptance_criteria=acceptance_criteria_text,
            non_goals=non_goals_text,
            context=context,
            controller_symbol_id=controller_symbol_id,
            controller_file_path=controller_file_path,
            controller_start_line=controller_symbol.start_line,
            controller_end_line=controller_symbol.end_line,
            controller_source_hash=controller_symbol.source_hash,
            service_evidence=service_evidence,
            service_evidence_json=service_evidence_json,
            goal_short=design_question.goal[:50] + "..." if len(design_question.goal) > 50 else design_question.goal,
            repo_commit=repo_commit
        )
        
        return prompt

    def _sample_negative_type(self) -> str | None:
        if not self.negative_types:
            return None
        if not isinstance(self.negative_ratio, (int, float)):
            return None
        if self.negative_ratio <= 0:
            return None
        if self.negative_rng.random() >= float(self.negative_ratio):
            return None
        return self.negative_rng.choice(self.negative_types)

    def _inject_negative_rules(self, prompt: str, negative_type: str | None) -> str:
        rules = self._build_negative_rules(negative_type)
        if not rules:
            return prompt
        marker = "# 输出要求"
        if marker in prompt:
            return prompt.replace(marker, f"{rules}\n\n{marker}", 1)
        return f"{prompt}\n\n{rules}"

    def _build_negative_rules(self, negative_type: str | None) -> str:
        if not negative_type:
            return ""
        rules_map = {
            "insufficient_evidence": [
                "说明证据不足，无法给出完整设计方案。",
                "列出需要补充的关键信息或代码位置。",
                "不得编造不存在的组件或配置。",
            ],
            "wrong_premise": [
                "指出问题前提不成立，并给出正确前提。",
                "基于证据解释前提错误的原因。",
            ],
            "conflict_spec": [
                "指出代码实现与需求描述存在冲突。",
                "以代码证据为准，并说明潜在风险。",
            ],
            "ambiguous_question": [
                "指出问题过于模糊或范围过大。",
                "给出需要澄清的关键点清单。",
            ],
        }
        rules = rules_map.get(negative_type, [])
        if not rules:
            return ""
        lines = "\n".join(f"- {rule}" for rule in rules)
        return (
            "## 负向样本要求\n"
            f"类型: {negative_type}\n"
            "请按以下规则回答：\n"
            f"{lines}"
        )

    def _build_quality(self, negative_type: str | None, design_question_id: str, context_symbols: int) -> dict:
        coverage = {"polarity": "positive"}
        if negative_type:
            coverage = {"polarity": "negative", "negative_type": negative_type}
        return {
            "schema_ok": True,
            "evidence_ok": True,
            "design_question_id": design_question_id,
            "context_symbols": context_symbols,
            "coverage": coverage,
        }

    def _write_retrieval_report(self) -> None:
        reports_dir = Path(self.config.get('output.reports_dir', 'data/reports'))
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / "design_retrieval_report.json"
        write_json(report_path, self.retrieval_stats)

    def _clean_json_output(self, output: str) -> str:
        """清理 LLM 输出，提取纯 JSON"""
        output = output.strip()

        if output.startswith("```json"):
            output = output[7:]
        elif output.startswith("```"):
            output = output[3:]

        if output.endswith("```"):
            output = output[:-3]

        output = output.strip()

        start_idx = output.find("{")
        end_idx = output.rfind("}")
        if start_idx != -1 and end_idx != -1:
            output = output[start_idx:end_idx + 1]

        return output
    
    def _validate_sample(
        self,
        sample: TrainingSample,
        design_question: DesignQuestion,
        repo_commit: str,
        symbols: list[CodeSymbol]
    ) -> tuple[bool, list[str]]:
        """校验训练样本"""
        errors = []
        
        # 创建符号索引
        symbol_index = {normalize_path_separators(s.symbol_id): s for s in symbols}
        
        # 1. 检查 repo_commit
        if sample.repo_commit != repo_commit:
            errors.append(f"repo_commit mismatch: {sample.repo_commit} != {repo_commit}")
        
        # 2. 检查 scenario
        if sample.scenario != "arch_design":
            errors.append(f"scenario should be 'arch_design', got '{sample.scenario}'")
        
        # 3. 检查 thought 结构
        if not sample.thought:
            errors.append("thought is missing")
        else:
            if not sample.thought.observations:
                errors.append("thought.observations is empty")
            if not sample.thought.inferences:
                errors.append("thought.inferences is empty")
            if not sample.thought.evidence_refs or len(sample.thought.evidence_refs) < 2:
                errors.append("thought.evidence_refs must have at least 2 items")
        
        # 4. 检查 evidence_refs
        if sample.thought and sample.thought.evidence_refs:
            for ref in sample.thought.evidence_refs:
                normalized_symbol_id = normalize_path_separators(ref.symbol_id)
                if normalized_symbol_id not in symbol_index:
                    errors.append(f"evidence_ref symbol_id not found: {ref.symbol_id}")
                else:
                    ref_symbol = symbol_index[normalized_symbol_id]
                    if ref.source_hash != ref_symbol.source_hash:
                        errors.append(
                            f"evidence_ref source_hash mismatch for {ref.symbol_id}"
                        )
                    normalized_ref_path = normalize_path_separators(ref.file_path)
                    normalized_symbol_path = normalize_path_separators(ref_symbol.file_path)
                    if normalized_ref_path != normalized_symbol_path:
                        errors.append(
                            f"evidence_ref file_path mismatch for {ref.symbol_id}"
                        )
        
        # 5. 检查 answer 结构（是否包含必要章节）
        required_sections = ['现状画像', '方案概述', '接口与数据变更', '迁移与回滚', '测试计划', '风险与权衡']
        missing_sections = [s for s in required_sections if s not in sample.answer]
        
        if len(missing_sections) > 2:  # 允许缺少最多 2 个章节
            errors.append(f"answer missing critical sections: {missing_sections}")
        
        # 6. 检查长度
        if len(sample.instruction) < 10:
            errors.append("instruction too short (< 10 chars)")
        if len(sample.answer) < 100:
            errors.append("answer too short (< 100 chars)")
        
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
    
    def _log_rejected(self, design_question: DesignQuestion, reason: str, raw_output: dict | None):
        """记录被拒绝的样本"""
        entry = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'design_question_id': design_question.id,
            'goal': design_question.goal,
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
        print(" 架构设计方案生成摘要")
        print("=" * 70)
        print(f"总设计问题数: {self.stats['total_design_questions']}")
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
        print(f"  - 设计问题文件: {self.design_questions_path}")
        print(f"  - 成功样本: {self.raw_output_path}")
        print(f"  - 失败样本: {self.rejected_path}")
        print("=" * 70)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='场景 2：架构设计方案生成器')
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
    
    args = parser.parse_args()
    
    # 加载配置
    config = Config()
    
    # 覆盖配置
    if args.max_samples:
        config._config['generation'] = config._config.get('generation', {})
        config._config['generation']['max_items'] = args.max_samples
    
    # 初始化生成器
    generator = DesignGenerator(config=config)
    
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
        logger.error(f"Design generation failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
