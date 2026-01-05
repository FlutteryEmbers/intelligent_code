"""
Automatic Requirement Generator - 自动生成架构设计需求

从代码仓库结构和符号中自动生成架构改进需求，用于 DesignGenerator。
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
from src.engine.llm_client import LLMClient

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


class RequirementGenerator:
    """
    自动需求生成器（轻量版）

    功能：
    1. 过滤候选符号（Controller/Service/Repository）
    2. 构造上下文与证据池
    3. LLM 生成需求（JSON）
    4. 归一化字段，尽量保留有效结果
    """

    # 架构层级注解
    CONTROLLER_ANNOTATIONS = {'RestController', 'Controller'}
    SERVICE_ANNOTATIONS = {'Service', 'Component'}
    REPOSITORY_ANNOTATIONS = {'Repository'}

    # 架构层级关键词
    CONTROLLER_KEYWORDS = ['controller', 'endpoint', 'api', 'rest']
    SERVICE_KEYWORDS = ['service', 'manager', 'handler']
    REPOSITORY_KEYWORDS = ['repository', 'dao', 'mapper']

    def __init__(self, config: Config | None = None):
        """初始化生成器"""
        self.config = config or Config()
        self.llm_client = LLMClient()

        # 加载 prompt 模板
        prompt_path = self.config.get(
            'auto_requirements.prompts.requirement_generation',
            'configs/prompts/auto_requirement_generation.txt'
        )
        self.prompt_template = load_prompt_template(prompt_path)

        # 从配置读取参数
        self.max_requirements = self.config.get('auto_requirements.max_requirements', 6)
        self.top_k_symbols = self.config.get('auto_requirements.top_k_symbols', 12)
        self.require_min_evidence = self.config.get('auto_requirements.require_min_evidence', 1)
        self.max_context_chars = self.config.get('auto_requirements.max_context_chars', 16000)
        self.seed = self.config.get('global.seed', 42)

        # Method profiles 配置（可选增强）
        self.use_method_profiles = self.config.get('auto_requirements.use_method_profiles', False)
        self.method_profiles_jsonl = Path(self.config.get(
            'auto_requirements.method_profiles_jsonl',
            'data/intermediate/method_profiles.jsonl'
        ))
        self.profiles_top_k = self.config.get('auto_requirements.profiles_top_k', 10)
        self.profiles_max_chars = self.config.get('auto_requirements.profiles_max_chars', 4000)

        # Batching 配置（可选）
        batching_config = self.config.get('auto_requirements.batching', {})
        self.batching_enabled = batching_config.get('enabled', False)
        self.batch_size = batching_config.get('batch_size', 2)
        self.max_batches = batching_config.get('max_batches', 5)

        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'auto_requirements.outputs.requirements_jsonl',
            'data/intermediate/requirements_auto.jsonl'
        ))
        self.rejected_jsonl = Path(self.config.get(
            'auto_requirements.outputs.rejected_jsonl',
            'data/intermediate/requirements_auto_rejected.jsonl'
        ))

        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)

        # 统计
        self.stats = {
            'total_symbols': 0,
            'filtered_symbols': 0,
            'generated_requirements': 0,
            'rejected_requirements': 0,
        }

        logger.info(
            "RequirementGenerator initialized: max_requirements=%s, top_k_symbols=%s, "
            "min_evidence=%s, use_method_profiles=%s, batching_enabled=%s, batch_size=%s",
            self.max_requirements,
            self.top_k_symbols,
            self.require_min_evidence,
            self.use_method_profiles,
            self.batching_enabled,
            self.batch_size,
        )

    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: str | None = None
    ) -> list[dict]:
        """
        从符号文件生成需求

        Args:
            symbols_path: 符号 JSONL 文件路径
            repo_commit: 仓库 commit

        Returns:
            list[dict]: 需求字典列表
        """
        start_time = time.time()
        logger.info(f"Starting requirement generation from {symbols_path}")

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
            requirements = self._generate_with_batching(context, evidence_pool, symbols_map)
        else:
            requirements = self._generate_single_batch(context, evidence_pool, symbols_map, self.max_requirements)

        elapsed = time.time() - start_time
        logger.info(
            "Requirement generation completed in %.1fs: total=%s, success=%s, rejected=%s",
            elapsed,
            len(requirements) + self.stats['rejected_requirements'],
            len(requirements),
            self.stats['rejected_requirements'],
        )

        self._save_requirements(requirements)
        return requirements

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
        normalized = self._normalize_requirements(parsed, symbols_map)
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
            remaining = self.max_requirements - len(collected)
            if remaining <= 0:
                break

            current_batch_size = min(self.batch_size, remaining)
            logger.info(
                "Batch %s/%s: Generating %s requirements",
                batch_idx + 1,
                self.max_batches,
                current_batch_size,
            )

            prompt = self._build_prompt(context, evidence_pool, current_batch_size)
            raw_output = self._call_llm(prompt)
            parsed = self._parse_llm_output(raw_output)
            batch_items = self._normalize_requirements(parsed, symbols_map, start_index=len(collected) + 1)

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
        candidates = []
        for symbol in symbols:
            if symbol.symbol_type != 'method':
                continue

            annotations = {ann.name for ann in symbol.annotations}
            if annotations & (self.CONTROLLER_ANNOTATIONS | self.SERVICE_ANNOTATIONS | self.REPOSITORY_ANNOTATIONS):
                candidates.append(symbol)
                continue

            path_lower = symbol.file_path.lower()
            qualified_lower = symbol.qualified_name.lower()
            if any(kw in path_lower or kw in qualified_lower for kw in
                   self.CONTROLLER_KEYWORDS + self.SERVICE_KEYWORDS + self.REPOSITORY_KEYWORDS):
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
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.CONTROLLER_ANNOTATIONS:
            return True
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        return any(kw in path_lower or kw in name_lower for kw in self.CONTROLLER_KEYWORDS)

    def _is_service(self, symbol: CodeSymbol) -> bool:
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.SERVICE_ANNOTATIONS:
            return True
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        return any(kw in path_lower or kw in name_lower for kw in self.SERVICE_KEYWORDS)

    def _is_repository(self, symbol: CodeSymbol) -> bool:
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.REPOSITORY_ANNOTATIONS:
            return True
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        return any(kw in path_lower or kw in name_lower for kw in self.REPOSITORY_KEYWORDS)

    def _build_context(self, symbols: list[CodeSymbol]) -> str:
        parts = []
        controllers = [s for s in symbols if self._is_controller(s)]
        services = [s for s in symbols if self._is_service(s)]
        repositories = [s for s in symbols if self._is_repository(s)]

        if controllers:
            parts.append("# Controller")
            for symbol in controllers:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.doc:
                    parts.append(f"Doc: {symbol.doc[:200]}...")
                parts.append(f"```java\n{symbol.source[:400]}...\n```")

        if services:
            parts.append("\n# Service")
            for symbol in services:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.doc:
                    parts.append(f"Doc: {symbol.doc[:200]}...")
                parts.append(f"```java\n{symbol.source[:400]}...\n```")

        if repositories:
            parts.append("\n# Repository")
            for symbol in repositories:
                parts.append(f"\n## {symbol.qualified_name}")
                parts.append(f"```java\n{symbol.source[:300]}...\n```")

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

    def _build_prompt(self, context: str, evidence_pool: str, max_requirements: int) -> str:
        return self.prompt_template.format(
            max_requirements=max_requirements,
            require_min_evidence=self.require_min_evidence,
            context=context,
            evidence_pool=evidence_pool
        )

    def _call_llm(self, prompt: str) -> str:
        logger.info("Calling LLM to generate requirements...")
        from langchain_core.messages import SystemMessage, HumanMessage

        system_prompt = (
            "You are a software architecture expert. "
            "Return only valid JSON, without markdown or extra text."
        )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
        response = self.llm_client.llm.invoke(messages)
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
            if 'requirements' in data and isinstance(data['requirements'], list):
                return data['requirements']
            # 兼容 requirement1/requirement2 形式
            if any(k.lower().startswith('requirement') for k in data.keys()):
                return [v for k, v in data.items() if isinstance(v, dict)]
            return [data]

        if isinstance(data, list):
            return data

        return []

    def _normalize_requirements(
        self,
        requirements: list,
        symbols_map: dict[str, CodeSymbol],
        start_index: int = 1
    ) -> list[dict]:
        normalized = []

        for idx, req in enumerate(requirements, start=start_index):
            norm = self._normalize_requirement(req, symbols_map, idx)
            if not norm:
                self.stats['rejected_requirements'] += 1
                continue
            normalized.append(norm)
            self.stats['generated_requirements'] += 1

        return normalized

    def _normalize_requirement(
        self,
        req: dict,
        symbols_map: dict[str, CodeSymbol],
        index: int
    ) -> dict | None:
        if not isinstance(req, dict):
            return None

        req_id = f"REQ-AUTO-{index:03d}"

        goal = req.get('goal') or req.get('description') or req.get('requirement') or req.get('title')
        if isinstance(goal, list):
            goal = goal[0] if goal else ""

        if not goal or not isinstance(goal, str):
            self._log_rejected({
                'requirement': req,
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
            symbol = symbols_map.get(symbol_id)
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

    def _save_requirements(self, requirements: list[dict]):
        if not requirements:
            logger.warning("No requirements to save")
            return
        with open(self.output_jsonl, 'w', encoding='utf-8') as f:
            for req in requirements:
                f.write(json.dumps(req, ensure_ascii=False) + '\n')
        logger.info(f"Saved {len(requirements)} requirements to {self.output_jsonl}")

    def _log_rejected(self, entry: dict):
        entry['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            with open(self.rejected_jsonl, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Failed to log rejected entry: {e}")

    def print_summary(self):
        print("\n" + "=" * 70)
        print(" 自动需求生成摘要")
        print("=" * 70)
        print(f"总符号数: {self.stats['total_symbols']}")
        print(f"过滤候选: {self.stats['filtered_symbols']}")
        print(f"成功生成: {self.stats['generated_requirements']}")
        print(f"生成失败: {self.stats['rejected_requirements']}")
        print(f"\n输出文件:")
        print(f"  - 需求文件: {self.output_jsonl}")
        print(f"  - 失败样本: {self.rejected_jsonl}")
        print("=" * 70)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='自动需求生成器')
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
        if 'auto_requirements' not in config._config:
            config._config['auto_requirements'] = {}
        if 'outputs' not in config._config['auto_requirements']:
            config._config['auto_requirements']['outputs'] = {}
        config._config['auto_requirements']['outputs']['requirements_jsonl'] = args.out

    generator = RequirementGenerator(config=config)

    try:
        requirements = generator.generate_from_repo(
            symbols_path=args.symbols,
            repo_commit=args.repo_commit
        )
        generator.print_summary()
        return 0 if requirements else 1
    except Exception as e:
        logger.error(f"Requirement generation failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
