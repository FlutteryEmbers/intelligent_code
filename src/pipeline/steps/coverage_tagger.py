"""
Coverage tagging step.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from src.pipeline.base_step import BaseStep
from src.utils.io.file_ops import read_jsonl, write_jsonl
from src.utils.data.coverage import (
    infer_intent,
    infer_module_span,
    infer_bucket,
    apply_evidence_bucket,
)


def _apply_coverage(sample: dict, default_source: str, evidence_cfg: dict) -> dict:
    """Apply coverage tags to a sample."""
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
        coverage["intent"] = infer_intent(text)

    if "module_span" not in coverage:
        coverage["module_span"] = infer_module_span(evidence_refs)

    if "bucket" not in coverage:
        text = f"{sample.get('instruction', '')} {sample.get('answer', '')}"
        bucket = infer_bucket(
            coverage.get("intent", "how_to"),
            coverage.get("module_span", "single"),
            text,
        )
        coverage["bucket"] = apply_evidence_bucket(bucket, evidence_count, evidence_cfg)

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
