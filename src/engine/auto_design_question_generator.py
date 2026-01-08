"""
Automatic Design Question Generator - 自动生成架构设计问题

从代码仓库结构和符号中自动生成架构设计问题，用于 DesignGenerator。
该版本去除过度的约束校验，保留基础能力与必要字段归一化。
"""
import json
import time
import random
from pathlib import Path
from typing import Generator

from src.utils.schemas import CodeSymbol
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.validator import normalize_path_separators
from src.utils.language_profile import load_language_profile
from src.engine.llm_client import LLMClient
from src.engine.auto_question_generator import load_scenario_templates

logger = get_logger(__name__)


def load_prompt_template(template_path: str | Path) -> str:
    """加载 prompt 模板文件"""
    path = Path(template_path)
    if not path.is_absolute():
        project_root = Path(__file__).parent.parent.parent
        candidate = project_root / path
        if candidate.exists():
            path = candidate
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class DesignQuestionGenerator:
    """
    自动设计问题生成器（轻量版）

    功能：
    1. 过滤候选符号（Controller/Service/Repository）
    2. 构造上下文与证据池
    3. LLM 生成设计问题（JSON）
    4. 归一化字段，尽量保留有效结果
    """

    def __init__(self, config: Config | None = None):
        """初始化生成器"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # Load language profile for layer rules
        self.language_profile = load_language_profile(self.config)

        # 加载 prompt 模板
        coverage_prompt = self.config.get('design_questions.prompts.coverage_generation')
        base_prompt = self.config.get(
            'design_questions.prompts.question_generation',
            'configs/prompts/design/auto_design_question_generation.txt',
        )
        prompt_path = self._resolve_prompt_path(coverage_prompt, base_prompt)
        self.prompt_template = load_prompt_template(prompt_path)

        # 从配置读取参数
        self.max_design_questions = self.config.get(
            'design_questions.max_questions',
            self.config.get('core.max_items', self.config.get('generation.max_items', 50)),
        )
        self.top_k_symbols = self.config.get(
            'core.retrieval_top_k',
            self.config.get('generation.retrieval_top_k', 6),
        )
        self.min_evidence_refs = self.config.get('design_questions.min_evidence_refs', 1)
        self.max_context_chars = self.config.get(
            'core.max_context_chars',
            self.config.get('generation.max_context_chars', 16000),
        )
        self.seed = self.config.get(
            'core.seed',
            self.config.get('generation.seed', 42),
        )
        self.coverage_config = self.config.get('design_questions.coverage', {}) or {}
        self.coverage_mode = self.coverage_config.get('mode', 'hybrid')
        self.constraint_strength = self.coverage_config.get('constraint_strength', 'hybrid')
        self.coverage_rng = random.Random(self.seed)
        self.diversity_config = self.coverage_config.get('diversity', {}) or {}
        self.diversity_mode = self.diversity_config.get('mode', 'off')
        self.question_type_targets = self.diversity_config.get('question_type_targets', {}) or {}
        self.scenario_config = self.coverage_config.get('scenario_injection', {}) or {}
        self.scenario_mode = self.scenario_config.get('mode', 'off')
        self.fuzzy_ratio = float(self.scenario_config.get('fuzzy_ratio', 0) or 0)
        self.scenario_templates = load_scenario_templates(
            self.scenario_config.get('templates_path')
        )

        # Method profiles 配置（可选增强）
        self.use_method_profiles = self.config.get('design_questions.use_method_profiles', False)
        self.method_profiles_jsonl = Path(self.config.get(
            'artifacts.method_profiles_jsonl',
            'data/intermediate/method_profiles.jsonl'
        ))
        self.profiles_top_k = self.config.get('design_questions.profiles_top_k', 10)
        self.profiles_max_chars = self.config.get('design_questions.profiles_max_chars', 4000)

        # Batching 配置（可选）
        batching_config = self.config.get('design_questions.batching', {})
        self.batching_enabled = batching_config.get('enabled', False)
        self.batch_size = self.config.get(
            'design_questions.batch_size',
            self.config.get('core.batch_size', self.config.get('generation.batch_size', 5)),
        )
        self.max_batches = batching_config.get('max_batches', 5)

        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.design_questions_jsonl',
            'data/intermediate/auto_questions/design_questions_auto.jsonl'
        ))
        self.rejected_jsonl = Path(self.config.get(
            'artifacts.design_questions_rejected_jsonl',
            'data/intermediate/rejected/design_questions_auto_rejected.jsonl'
        ))

        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_jsonl.parent.mkdir(parents=True, exist_ok=True)

        # 统计
        self.stats = {
            'total_symbols': 0,
            'filtered_symbols': 0,
            'generated_design_questions': 0,
            'rejected_design_questions': 0,
        }

        logger.info(
            "DesignQuestionGenerator initialized: max_design_questions=%s, top_k_symbols=%s, "
            "min_evidence=%s, use_method_profiles=%s, batching_enabled=%s, batch_size=%s",
            self.max_design_questions,
            self.top_k_symbols,
            self.min_evidence_refs,
            self.use_method_profiles,
            self.batching_enabled,
            self.batch_size,
        )

    def _resolve_prompt_path(self, preferred: str | None, fallback: str) -> str:
        if preferred:
            preferred_path = Path(preferred)
            if preferred_path.exists():
                return str(preferred_path)
            logger.warning("Coverage prompt not found, fallback to base prompt: %s", preferred_path)
        return fallback

    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: str | None = None
    ) -> list[dict]:
        """
        从符号文件生成设计问题

        Args:
            symbols_path: 符号 JSONL 文件路径
            repo_commit: 仓库 commit

        Returns:
            list[dict]: 设计问题字典列表
        """
        start_time = time.time()
        logger.info(f"Starting design question generation from {symbols_path}")

        symbols = self._load_symbols(symbols_path)
        self.stats['total_symbols'] = len(symbols)

        if not symbols:
            logger.warning("No symbols loaded")
            return []

        if not repo_commit:
            repo_commit = symbols[0].repo_commit
            logger.info(f"Using repo_commit from symbols: {repo_commit}")

        candidates = self._filter_candidates(symbols)
        self.stats['filtered_symbols'] = len(candidates)

        if not candidates:
            logger.warning("No candidates after filtering")
            return []

        logger.info(f"Filtered to {len(candidates)} candidate symbols")

        selected_symbols = self._select_top_k_symbols(candidates)
        logger.info(f"Selected {len(selected_symbols)} symbols for context")

        context = self._build_context(selected_symbols)
        evidence_pool = self._build_evidence_pool(selected_symbols)

        if self.use_method_profiles:
            profiles = self._load_method_profiles(repo_commit)
            if profiles:
                profiles_context = self._build_profiles_context(profiles)
                if profiles_context:
                    context = context + "\n\n" + profiles_context
                    logger.info(
                        "Enhanced context with %s method profiles (%s chars)",
                        len(profiles),
                        len(profiles_context),
                    )

        symbols_map = {s.symbol_id: s for s in symbols}

        if self.batching_enabled:
            design_questions = self._generate_with_batching(context, evidence_pool, symbols_map)
        else:
            design_questions = self._generate_single_batch(
                context,
                evidence_pool,
                symbols_map,
                self.max_design_questions,
            )

        elapsed = time.time() - start_time
        logger.info(
            "Design question generation completed in %.1fs: total=%s, success=%s, rejected=%s",
            elapsed,
            len(design_questions) + self.stats['rejected_design_questions'],
            len(design_questions),
            self.stats['rejected_design_questions'],
        )

        self._save_design_questions(design_questions)
        return design_questions

    def _generate_single_batch(
        self,
        context: str,
        evidence_pool: str,
        symbols_map: dict[str, CodeSymbol],
        target_count: int
    ) -> list[dict]:
        prompt = self._build_prompt(context, evidence_pool, target_count)
        raw_output = self._call_llm(prompt)
        parsed = self._parse_llm_output(raw_output)
        normalized = self._normalize_design_questions(parsed, symbols_map)
        return normalized

    def _generate_with_batching(
        self,
        context: str,
        evidence_pool: str,
        symbols_map: dict[str, CodeSymbol]
    ) -> list[dict]:
        collected: list[dict] = []
        seen_goals: set[str] = set()

        for batch_idx in range(self.max_batches):
            remaining = self.max_design_questions - len(collected)
            if remaining <= 0:
                break

            current_batch_size = min(self.batch_size, remaining)
            logger.info(
                "Batch %s/%s: Generating %s design questions",
                batch_idx + 1,
                self.max_batches,
                current_batch_size,
            )

            prompt = self._build_prompt(context, evidence_pool, current_batch_size)
            raw_output = self._call_llm(prompt)
            parsed = self._parse_llm_output(raw_output)
            batch_items = self._normalize_design_questions(
                parsed,
                symbols_map,
                start_index=len(collected) + 1,
            )

            added = 0
            for item in batch_items:
                goal_key = (item.get('goal') or '').strip().lower()
                if not goal_key or goal_key in seen_goals:
                    continue
                seen_goals.add(goal_key)
                collected.append(item)
                added += 1

            logger.info(
                "Batch %s results: parsed=%s, added=%s, total=%s",
                batch_idx + 1,
                len(batch_items),
                added,
                len(collected),
            )

        return collected

    def _load_symbols(self, symbols_path: Path | str) -> list[CodeSymbol]:
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

    def _filter_candidates(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """Filter candidate symbols using language profile rules"""
        candidates = []
        
        # Collect all layer rules
        design_layers = self.language_profile.get('design', {}).get('layers', {})
        all_annotations = set()
        all_decorators = set()
        all_keywords = []
        
        for layer_name in ['controller', 'service', 'repository']:
            layer_rules = design_layers.get(layer_name, {})
            all_annotations.update(layer_rules.get('annotations', []))
            all_decorators.update(layer_rules.get('decorators', []))
            all_keywords.extend(layer_rules.get('name_keywords', []))
            all_keywords.extend(layer_rules.get('path_keywords', []))
        
        for symbol in symbols:
            if symbol.symbol_type != 'method':
                continue

            annotations = {ann.name for ann in symbol.annotations}
            # Check both annotations (Java) and decorators (Python)
            if annotations & (all_annotations | all_decorators):
                candidates.append(symbol)
                continue

            # Check keywords in path and qualified name
            path_lower = symbol.file_path.lower()
            qualified_lower = symbol.qualified_name.lower()
            if any(kw in path_lower or kw in qualified_lower for kw in all_keywords):
                candidates.append(symbol)

        return candidates

    def _select_top_k_symbols(self, candidates: list[CodeSymbol]) -> list[CodeSymbol]:
        controllers = [s for s in candidates if self._is_controller(s)]
        services = [s for s in candidates if self._is_service(s)]
        repositories = [s for s in candidates if self._is_repository(s)]

        random.seed(self.seed)
        k = min(self.top_k_symbols, len(candidates))

        selected = []
        controller_quota = min(len(controllers), max(k // 3, 1))
        selected.extend(random.sample(controllers, controller_quota) if len(controllers) >= controller_quota else controllers)

        service_quota = min(len(services), max(k // 3, 1))
        selected.extend(random.sample(services, service_quota) if len(services) >= service_quota else services)

        remaining = k - len(selected)
        if remaining > 0 and repositories:
            repo_quota = min(len(repositories), remaining)
            selected.extend(random.sample(repositories, repo_quota) if len(repositories) >= repo_quota else repositories)

        if len(selected) < k:
            remaining_candidates = [s for s in candidates if s not in selected]
            if remaining_candidates:
                supplement = min(len(remaining_candidates), k - len(selected))
                selected.extend(random.sample(remaining_candidates, supplement))

        return selected[:k]

    def _is_controller(self, symbol: CodeSymbol) -> bool:
        """Check if symbol is a controller using language profile rules"""
        layer_rules = self.language_profile.get('design', {}).get('layers', {}).get('controller', {})
        
        # Check annotations (Java) or decorators (Python)
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & set(layer_rules.get('annotations', [])):
            return True
        if annotations & set(layer_rules.get('decorators', [])):
            return True
        
        # Check name and path keywords
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        name_keywords = layer_rules.get('name_keywords', [])
        path_keywords = layer_rules.get('path_keywords', [])
        
        return any(kw in name_lower for kw in name_keywords) or any(kw in path_lower for kw in path_keywords)

    def _is_service(self, symbol: CodeSymbol) -> bool:
        """Check if symbol is a service using language profile rules"""
        layer_rules = self.language_profile.get('design', {}).get('layers', {}).get('service', {})
        
        # Check annotations (Java) or decorators (Python)
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & set(layer_rules.get('annotations', [])):
            return True
        if annotations & set(layer_rules.get('decorators', [])):
            return True
        
        # Check name and path keywords
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        name_keywords = layer_rules.get('name_keywords', [])
        path_keywords = layer_rules.get('path_keywords', [])
        
        return any(kw in name_lower for kw in name_keywords) or any(kw in path_lower for kw in path_keywords)

    def _is_repository(self, symbol: CodeSymbol) -> bool:
        """Check if symbol is a repository using language profile rules"""
        layer_rules = self.language_profile.get('design', {}).get('layers', {}).get('repository', {})
        
        # Check annotations (Java) or decorators (Python)
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & set(layer_rules.get('annotations', [])):
            return True
        if annotations & set(layer_rules.get('decorators', [])):
            return True
        
        # Check name and path keywords
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        name_keywords = layer_rules.get('name_keywords', [])
        path_keywords = layer_rules.get('path_keywords', [])
        
        return any(kw in name_lower for kw in name_keywords) or any(kw in path_lower for kw in path_keywords)

    def _build_context(self, symbols: list[CodeSymbol]) -> str:
        """Build context string with language-specific code blocks"""
        parts = []
        controllers = [s for s in symbols if self._is_controller(s)]
        services = [s for s in symbols if self._is_service(s)]
        repositories = [s for s in symbols if self._is_repository(s)]
        
        # Get language name for code blocks
        language_name = self.language_profile.get('language', 'java')

        if controllers:
            parts.append("# Controller")
            for symbol in controllers:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.doc:
                    parts.append(f"Doc: {symbol.doc[:200]}...")
                parts.append(f"```{language_name}\n{symbol.source[:400]}...\n```")

        if services:
            parts.append("\n# Service")
            for symbol in services:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.doc:
                    parts.append(f"Doc: {symbol.doc[:200]}...")
                parts.append(f"```{language_name}\n{symbol.source[:400]}...\n```")

        if repositories:
            parts.append("\n# Repository")
            for symbol in repositories:
                parts.append(f"\n## {symbol.qualified_name}")
                parts.append(f"```{language_name}\n{symbol.source[:300]}...\n```")

        context = "\n".join(parts)
        if len(context) > self.max_context_chars:
            context = context[:self.max_context_chars] + "\n\n... (context truncated)"
        return context

    def _build_evidence_pool(self, symbols: list[CodeSymbol]) -> str:
        parts = []
        for symbol in symbols:
            parts.append(
                "\n".join([
                    "{",
                    f'  "symbol_id": "{symbol.symbol_id}",',
                    f'  "file_path": "{symbol.file_path}",',
                    f'  "start_line": {symbol.start_line},',
                    f'  "end_line": {symbol.end_line},',
                    f'  "source_hash": "{symbol.source_hash}",',
                    f'  "qualified_name": "{symbol.qualified_name}"',
                    "}"
                ])
            )
        return ",".join(parts)

    def _load_method_profiles(self, repo_commit: str | None = None) -> list[dict]:
        if not self.method_profiles_jsonl.exists():
            return []
        profiles = []
        try:
            with open(self.method_profiles_jsonl, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        profile = json.loads(line)
                        if repo_commit and profile.get('repo_commit') and profile['repo_commit'] != repo_commit:
                            continue
                        profiles.append(profile)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse profile at line {line_num}: {e}")
                        continue
        except Exception as e:
            logger.warning(f"Failed to load method profiles: {e}")
            return []
        return profiles

    def _build_profiles_context(self, profiles: list[dict]) -> str:
        if not profiles:
            return ""
        parts = ["## Method Profiles"]
        for profile in profiles[:self.profiles_top_k]:
            if 'qualified_name' in profile:
                parts.append(f"### {profile['qualified_name']}")
            if 'summary' in profile and profile['summary']:
                parts.append(profile['summary'])
            if profile.get('business_rules'):
                parts.append("Rules: " + "; ".join(profile['business_rules']))
            parts.append("")
        result = "\n".join(parts)
        if len(result) > self.profiles_max_chars:
            result = result[:self.profiles_max_chars] + "\n\n... (profiles truncated)"
        return result

    def _weighted_choice(self, weights: dict[str, float], default: str) -> str:
        if not isinstance(weights, dict):
            return default
        total = sum(float(value) for value in weights.values())
        if total <= 0:
            return default
        threshold = self.coverage_rng.random() * total
        cumulative = 0.0
        for key, value in weights.items():
            cumulative += float(value)
            if threshold <= cumulative:
                return key
        return default

    def _sample_coverage_target(self) -> tuple[str, str]:
        if self.coverage_mode not in ("upstream", "hybrid"):
            return "high", "design"
        bucket = self._weighted_choice(
            self.coverage_config.get("targets", {}),
            "high",
        )
        intent = self._weighted_choice(
            self.coverage_config.get("intent_targets", {}),
            "design",
        )
        return bucket, intent

    def _sample_question_type(self) -> str:
        if self.diversity_mode != "quota":
            return "architecture"
        return self._weighted_choice(self.question_type_targets, "architecture")

    def _build_scenario_constraints(self) -> str:
        if self.scenario_mode != "ratio":
            return ""
        if not self.scenario_templates or self.fuzzy_ratio <= 0:
            return ""
        if self.coverage_rng.random() >= self.fuzzy_ratio:
            return ""
        return self.coverage_rng.choice(self.scenario_templates)

    def _resolve_constraint_strength(self, bucket: str) -> str:
        strength = self.constraint_strength
        if strength == "hybrid":
            return "strong" if bucket in ("mid", "hard") else "weak"
        if strength in ("strong", "weak"):
            return strength
        return "weak"

    def _build_constraint_rules(self, bucket: str) -> tuple[str, str]:
        strength = self._resolve_constraint_strength(bucket)
        if strength == "strong":
            rules = (
                "Strong constraints:\n"
                "- Include trade-offs, constraints, or implicit requirements.\n"
                "- Highlight risks, boundary conditions, or backward compatibility.\n"
                "- Keep the question specific to the evidence pool and design context."
            )
        else:
            rules = (
                "Weak constraints:\n"
                "- Keep the question concise and focused on a single goal.\n"
                "- Use natural wording but stay grounded in the evidence pool."
            )
        return strength, rules

    def _build_prompt(self, context: str, evidence_pool: str, max_design_questions: int) -> str:
        language_name = self.language_profile.get('language', 'java')
        coverage_bucket, coverage_intent = self._sample_coverage_target()
        question_type = self._sample_question_type()
        scenario_constraints = self._build_scenario_constraints()
        constraint_strength, constraint_rules = self._build_constraint_rules(coverage_bucket)
        return self.prompt_template.format(
            language=language_name.capitalize(),
            max_design_questions=max_design_questions,
            min_evidence_refs=self.min_evidence_refs,
            context=context,
            evidence_pool=evidence_pool,
            coverage_bucket=coverage_bucket,
            coverage_intent=coverage_intent,
            question_type=question_type,
            scenario_constraints=scenario_constraints or "None",
            constraint_strength=constraint_strength,
            constraint_rules=constraint_rules,
        )

    def _call_llm(self, prompt: str) -> str:
        logger.info("Calling LLM to generate design questions...")
        from langchain_core.messages import SystemMessage, HumanMessage

        language_name = self.language_profile.get('language', 'java').capitalize()
        system_prompt = (
            f"You are a software architecture expert specializing in {language_name} projects. "
            "Return only valid JSON, without markdown or extra text."
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
        response = self.llm_client.llm.invoke(
            messages,
            max_tokens=self.llm_client.max_tokens  # 显式传递以确保参数生效
        )
        return response.content

    def _parse_llm_output(self, raw_output: str) -> list[dict]:
        import re

        output = raw_output.strip()
        output = re.sub(r'<\|im_(?:start|end|sep)\|>\s*', '', output)
        output = re.sub(r'```json\s*', '', output)
        output = re.sub(r'```\s*', '', output)
        output = output.strip()

        # 找到第一个 JSON 开始
        json_start = -1
        for i, char in enumerate(output):
            if char in '{[':
                json_start = i
                break
        if json_start == -1:
            logger.warning("No JSON object found in LLM output")
            return []

        output = output[json_start:]

        # 括号匹配截取完整 JSON
        depth = 0
        json_end = -1
        in_string = False
        escape_next = False

        for i, char in enumerate(output):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char in '{[':
                    depth += 1
                elif char in '}]':
                    depth -= 1
                    if depth == 0:
                        json_end = i
                        break

        if json_end == -1:
            logger.warning("Could not find complete JSON; using raw output")
            json_text = output
        else:
            json_text = output[:json_end + 1]

        json_text = re.sub(r',\s*([\]}])', r'\1', json_text)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM output as JSON: {e}")
            return []

        if isinstance(data, dict):
            if 'design_questions' in data and isinstance(data['design_questions'], list):
                return data['design_questions']
            if any(k.lower().startswith('design_question') for k in data.keys()):
                return [v for k, v in data.items() if isinstance(v, dict)]
            return [data]

        if isinstance(data, list):
            return data

        return []

    def _normalize_design_questions(
        self,
        design_questions: list,
        symbols_map: dict[str, CodeSymbol],
        start_index: int = 1
    ) -> list[dict]:
        normalized = []

        for idx, req in enumerate(design_questions, start=start_index):
            norm = self._normalize_design_question(req, symbols_map, idx)
            if not norm:
                self.stats['rejected_design_questions'] += 1
                continue
            normalized.append(norm)
            self.stats['generated_design_questions'] += 1

        return normalized

    def _normalize_design_question(
        self,
        req: dict,
        symbols_map: dict[str, CodeSymbol],
        index: int
    ) -> dict | None:
        if not isinstance(req, dict):
            return None

        req_id = f"DQ-AUTO-{index:03d}"

        goal = req.get('goal') or req.get('description') or req.get('question') or req.get('title')
        if isinstance(goal, list):
            goal = goal[0] if goal else ""

        if not goal or not isinstance(goal, str):
            self._log_rejected({
                'design_question': req,
                'reason': 'missing_goal'
            })
            return None

        constraints = self._coerce_list(req.get('constraints') or req.get('constraint'))
        acceptance = self._coerce_list(req.get('acceptance_criteria') or req.get('acceptance') or req.get('criteria'))
        non_goals = self._coerce_list(req.get('non_goals') or req.get('non_goal'))

        evidence_refs = self._normalize_evidence_refs(req, symbols_map)

        return {
            'id': req_id,
            'goal': goal,
            'constraints': constraints,
            'acceptance_criteria': acceptance,
            'non_goals': non_goals,
            'evidence_refs': evidence_refs,
        }

    def _coerce_list(self, value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [value]
        return []

    def _normalize_evidence_refs(self, req: dict, symbols_map: dict[str, CodeSymbol]) -> list[dict]:
        refs = req.get('evidence_refs')
        if isinstance(refs, dict):
            refs = [refs]
        if isinstance(refs, list) and refs:
            cleaned = []
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                if all(k in ref for k in ['symbol_id', 'file_path', 'start_line', 'end_line', 'source_hash']):
                    cleaned.append(ref)
            if cleaned:
                return cleaned

        # 兼容 symbol_id / symbol_ids
        symbol_ids = []
        if isinstance(req.get('symbol_id'), str):
            symbol_ids.append(req['symbol_id'])
        if isinstance(req.get('symbol_ids'), list):
            symbol_ids.extend([s for s in req['symbol_ids'] if isinstance(s, str)])

        # 兼容 code_location/qualified_name/file_path
        if not symbol_ids:
            location = req.get('code_location') if isinstance(req.get('code_location'), dict) else {}
            qn = location.get('qualified_name') or req.get('qualified_name')
            fp = location.get('file_path') or req.get('file_path')
            if qn:
                match = next((s for s in symbols_map.values() if s.qualified_name == qn), None)
                if match:
                    symbol_ids.append(match.symbol_id)
            if not symbol_ids and fp:
                match = next((s for s in symbols_map.values() if s.file_path == fp), None)
                if match:
                    symbol_ids.append(match.symbol_id)

        evidence = []
        for symbol_id in symbol_ids:
            # 标准化路径以支持跨平台
            normalized_symbol_id = normalize_path_separators(symbol_id)
            symbol = symbols_map.get(normalized_symbol_id)
            if not symbol:
                continue
            evidence.append({
                'symbol_id': symbol.symbol_id,
                'file_path': symbol.file_path,
                'start_line': symbol.start_line,
                'end_line': symbol.end_line,
                'source_hash': symbol.source_hash,
            })

        return evidence

    def _save_design_questions(self, design_questions: list[dict]):
        if not design_questions:
            logger.warning("No design questions to save")
            return
        with open(self.output_jsonl, 'w', encoding='utf-8') as f:
            for req in design_questions:
                f.write(json.dumps(req, ensure_ascii=False) + '\n')
        logger.info(f"Saved {len(design_questions)} design questions to {self.output_jsonl}")

    def _log_rejected(self, entry: dict):
        entry['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            with open(self.rejected_jsonl, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Failed to log rejected entry: {e}")

    def print_summary(self):
        print("\n" + "=" * 70)
        print(" 自动设计问题生成摘要")
        print("=" * 70)
        print(f"总符号数: {self.stats['total_symbols']}")
        print(f"过滤候选: {self.stats['filtered_symbols']}")
        print(f"成功生成: {self.stats['generated_design_questions']}")
        print(f"生成失败: {self.stats['rejected_design_questions']}")
        print(f"\n输出文件:")
        print(f"  - 设计问题文件: {self.output_jsonl}")
        print(f"  - 失败样本: {self.rejected_jsonl}")
        print("=" * 70)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='自动设计问题生成器')
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
        '--out',
        default=None,
        help='输出文件路径（可选，默认从配置读取）'
    )

    args = parser.parse_args()

    config = Config()

    if args.out:
        if 'artifacts' not in config._config:
            config._config['artifacts'] = {}
        config._config['artifacts']['design_questions_jsonl'] = args.out

    generator = DesignQuestionGenerator(config=config)

    try:
        design_questions = generator.generate_from_repo(
            symbols_path=args.symbols,
            repo_commit=args.repo_commit
        )
        generator.print_summary()
        return 0 if design_questions else 1
    except Exception as e:
        logger.error(f"Design question generation failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
