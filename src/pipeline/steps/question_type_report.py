"""
Question type distribution reporting.
"""
from __future__ import annotations

from pathlib import Path

from src.pipeline.base_step import BaseStep
from src.utils.io.file_ops import read_jsonl, write_json
from src.utils.data.coverage import compute_distribution


def _compare_targets(targets: dict, actual: dict, max_delta: float) -> list[str]:
    warnings = []
    total = actual.get("total", 0)
    ratios = actual.get("ratios", {})
    if total == 0:
        return warnings
    for key, target in targets.items():
        actual_ratio = ratios.get(key, 0.0)
        delta = abs(actual_ratio - float(target))
        if delta > max_delta:
            warnings.append(
                f"{key} ratio {actual_ratio:.4f} exceeds target {target:.4f} by {delta:.4f}"
            )
    return warnings


class QuestionTypeReportStep(BaseStep):
    """Report question_type distribution and regression warnings."""

    @property
    def name(self) -> str:
        return "question_type_report"

    @property
    def display_name(self) -> str:
        return "Step 7.5: Question Type Report"

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

        report_path = Path(
            artifacts.get(
                "question_type_report_json",
                Path(self.config.get("output.reports_dir", "data/reports"))
                / "question_type_report.json",
            )
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        qa_div = self.config.get("question_answer.coverage", {}).get("diversity", {}) or {}
        design_div = self.config.get("design_questions.coverage", {}).get("diversity", {}) or {}

        qa_targets = qa_div.get("question_type_targets", {}) or {}
        design_targets = design_div.get("question_type_targets", {}) or {}
        qa_reg = qa_div.get("regression", {}) or {}
        design_reg = design_div.get("regression", {}) or {}

        qa_samples = read_jsonl(qa_clean_path) if qa_clean_path.exists() else []
        design_samples = read_jsonl(design_clean_path) if design_clean_path.exists() else []

        qa_dist = compute_distribution(qa_samples, "quality.coverage.question_type")
        design_dist = compute_distribution(design_samples, "quality.coverage.question_type")

        qa_max_delta = float(qa_reg.get("max_delta", 0.1))
        design_max_delta = float(design_reg.get("max_delta", 0.1))
        qa_warn = []
        design_warn = []
        if qa_reg.get("enabled", False):
            qa_warn = _compare_targets(qa_targets, qa_dist, qa_max_delta)
        if design_reg.get("enabled", False):
            design_warn = _compare_targets(design_targets, design_dist, design_max_delta)

        report = {
            "qa": {
                "distribution": qa_dist,
                "targets": qa_targets,
                "regression": {
                    "enabled": bool(qa_reg.get("enabled", False)),
                    "max_delta": qa_max_delta,
                    "warnings": qa_warn,
                },
            },
            "design": {
                "distribution": design_dist,
                "targets": design_targets,
                "regression": {
                    "enabled": bool(design_reg.get("enabled", False)),
                    "max_delta": design_max_delta,
                    "warnings": design_warn,
                },
            },
        }

        write_json(report_path, report)

        warnings = qa_warn + design_warn
        if warnings:
            for item in warnings:
                self.logger.warning("Question type regression: %s", item)

        return {
            "status": "success",
            "report_path": str(report_path),
            "qa_total": qa_dist.get("total", 0),
            "design_total": design_dist.get("total", 0),
            "warnings": warnings,
        }
