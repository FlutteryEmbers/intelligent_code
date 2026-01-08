"""
Coverage tagging step.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from src.pipeline.base_step import BaseStep
from src.utils import read_jsonl, write_jsonl
from src.utils.validator import normalize_path_separators


INTENT_KEYWORDS = {
    "config": ["config", "yaml", "properties", "flag", "env", "配置", "开关"],
    "error": ["error", "exception", "fail", "timeout", "retry", "code", "错误", "异常", "失败", "超时", "重试", "错误码"],
    "deploy": ["deploy", "rollout", "release", "migration", "部署", "发布", "上线", "迁移"],
    "impact": ["impact", "change", "break", "影响", "变更"],
    "perf": ["latency", "throughput", "performance", "perf", "性能", "吞吐", "延迟"],
    "consistency": ["consistency", "transaction", "一致性", "事务"],
    "auth": ["auth", "authorize", "permission", "权限", "鉴权", "认证"],
    "flow": ["flow", "workflow", "流程", "链路", "路径"],
    "how_to": ["how to", "如何", "怎样", "如何做", "如何使用"],
    "compatibility": ["compatibility", "legacy", "兼容", "历史"],
    "edge": ["edge", "corner", "边界", "极端"],
}

HARD_KEYWORDS = [
    "legacy",
    "compatibility",
    "invariant",
    "gotcha",
    "pitfall",
    "反直觉",
    "隐含",
    "历史",
    "兼容",
    "坑",
    "陷阱",
]


def _infer_intent(text: str) -> str:
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return intent
    return "how_to"


def _infer_module_span(evidence_refs: list[dict]) -> str:
    if not evidence_refs:
        return "single"
    prefixes = set()
    for ref in evidence_refs:
        path = ref.get("file_path") or ""
        if not path:
            continue
        normalized = normalize_path_separators(path)
        prefix = normalized.split("/")[0] if normalized else ""
        if prefix:
            prefixes.add(prefix)
    return "multi" if len(prefixes) > 1 else "single"


def _infer_bucket(intent: str, module_span: str, text: str) -> str:
    lowered = text.lower()
    if intent in ("compatibility", "edge") or any(kw in lowered for kw in HARD_KEYWORDS):
        return "hard"
    if module_span == "multi" or intent in ("perf", "consistency"):
        return "mid"
    return "high"


def _apply_evidence_bucket(
    bucket: str,
    evidence_count: int,
    evidence_cfg: dict,
) -> str:
    mode = evidence_cfg.get("mode", "off")
    if mode not in ("assist", "strict"):
        return bucket

    try:
        mid_min = int(evidence_cfg.get("mid_min", 0))
    except (TypeError, ValueError):
        mid_min = 0
    try:
        hard_min = int(evidence_cfg.get("hard_min", 0))
    except (TypeError, ValueError):
        hard_min = 0

    if mode == "strict":
        if hard_min and evidence_count >= hard_min:
            return "hard"
        if mid_min and evidence_count >= mid_min:
            return "mid"
        return "high"

    candidate = bucket
    if hard_min and evidence_count >= hard_min:
        candidate = "hard"
    elif mid_min and evidence_count >= mid_min:
        candidate = "mid"

    rank = {"high": 0, "mid": 1, "hard": 2}
    base_rank = rank.get(bucket, 0)
    cand_rank = rank.get(candidate, base_rank)
    return candidate if cand_rank > base_rank else bucket


def _apply_coverage(sample: dict, default_source: str, evidence_cfg: dict) -> dict:
    quality = sample.get("quality") or {}
    coverage = quality.get("coverage") or {}

    scenario = coverage.get("scenario") or sample.get("scenario", "")
    evidence_refs = (
        sample.get("thought", {}).get("evidence_refs")
        if isinstance(sample.get("thought"), dict)
        else []
    ) or []
    evidence_count = len(evidence_refs) if isinstance(evidence_refs, list) else 0

    if "intent" not in coverage:
        text = f"{sample.get('instruction', '')} {sample.get('answer', '')}"
        coverage["intent"] = _infer_intent(text)

    if "module_span" not in coverage:
        coverage["module_span"] = _infer_module_span(evidence_refs)

    if "bucket" not in coverage:
        text = f"{sample.get('instruction', '')} {sample.get('answer', '')}"
        bucket = _infer_bucket(
            coverage.get("intent", "how_to"),
            coverage.get("module_span", "single"),
            text,
        )
        coverage["bucket"] = _apply_evidence_bucket(bucket, evidence_count, evidence_cfg)

    coverage.setdefault("source", default_source)
    coverage.setdefault("scenario", scenario)

    quality["coverage"] = coverage
    sample["quality"] = quality
    return sample


class CoverageTaggerStep(BaseStep):
    """Tag samples with coverage labels."""

    @property
    def name(self) -> str:
        return "coverage_tagger"

    @property
    def display_name(self) -> str:
        return "Step 6: Coverage Tagging"

    def _tag_file(self, path: Path, default_source: str, evidence_cfg: dict) -> dict:
        if not path.exists():
            self.logger.info("Coverage tagging skipped, file not found: %s", path)
            return {"path": str(path), "tagged": 0, "total": 0}

        samples = read_jsonl(path)
        if not samples:
            self.logger.info("Coverage tagging skipped, empty file: %s", path)
            return {"path": str(path), "tagged": 0, "total": 0}

        tagged = [_apply_coverage(sample, default_source, evidence_cfg) for sample in samples]
        write_jsonl(path, tagged)

        counts = defaultdict(int)
        for sample in tagged:
            bucket = sample.get("quality", {}).get("coverage", {}).get("bucket", "unknown")
            counts[bucket] += 1

        return {
            "path": str(path),
            "tagged": len(tagged),
            "total": len(samples),
            "bucket_counts": dict(counts),
        }

    def execute(self) -> dict:
        artifacts = self.config.get("artifacts", {})
        qa_clean_path = Path(
            artifacts.get(
                "qa_clean_jsonl",
                self.paths.get("qa_clean_jsonl", "data/intermediate/clean/qa_clean.jsonl"),
            )
        )
        design_clean_path = Path(
            artifacts.get(
                "design_clean_jsonl",
                self.paths.get(
                    "design_clean_jsonl",
                    "data/intermediate/clean/design_clean.jsonl",
                ),
            )
        )

        qa_cov = self.config.get("question_answer.coverage", {}) or {}
        design_cov = self.config.get("design_questions.coverage", {}) or {}
        qa_evidence_cfg = qa_cov.get("evidence_refs", {}) or {}
        design_evidence_cfg = design_cov.get("evidence_refs", {}) or {}

        qa_result = (
            self._tag_file(qa_clean_path, "auto", qa_evidence_cfg)
            if qa_cov.get("labeler", "rule") == "rule"
            else {"path": str(qa_clean_path), "tagged": 0, "total": 0, "skipped": True}
        )
        design_result = (
            self._tag_file(design_clean_path, "auto", design_evidence_cfg)
            if design_cov.get("labeler", "rule") == "rule"
            else {"path": str(design_clean_path), "tagged": 0, "total": 0, "skipped": True}
        )

        return {
            "status": "success",
            "qa": qa_result,
            "design": design_result,
        }
