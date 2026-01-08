"""
Coverage sampling step.
"""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from src.pipeline.base_step import BaseStep
from src.utils import read_jsonl, write_jsonl, write_json


BUCKETS = ("high", "mid", "hard")
DEFAULT_TARGETS = {"high": 0.8, "mid": 0.15, "hard": 0.05}
FALLBACK_CHAIN = {
    "hard": ("mid", "high"),
    "mid": ("high",),
    "high": (),
}


def _normalize_targets(targets: dict | None) -> tuple[dict[str, float], bool]:
    if not isinstance(targets, dict):
        return DEFAULT_TARGETS.copy(), True
    total = sum(float(value) for value in targets.values())
    if total <= 0:
        return DEFAULT_TARGETS.copy(), True
    normalized = {bucket: float(targets.get(bucket, 0.0)) / total for bucket in BUCKETS}
    return normalized, False


def _desired_counts(total: int, targets: dict[str, float]) -> dict[str, int]:
    counts = {bucket: int(round(total * targets.get(bucket, 0.0))) for bucket in BUCKETS}
    delta = total - sum(counts.values())
    if delta != 0:
        ordered = sorted(targets.items(), key=lambda item: item[1], reverse=True)
        idx = 0
        step = 1 if delta > 0 else -1
        for _ in range(abs(delta)):
            bucket = ordered[idx % len(ordered)][0]
            counts[bucket] = max(0, counts[bucket] + step)
            idx += 1
    return counts


def _pick_samples(rng: random.Random, samples: list[dict], count: int) -> tuple[list[dict], list[dict]]:
    if count <= 0:
        return [], samples
    if count >= len(samples):
        return samples, []
    rng.shuffle(samples)
    return samples[:count], samples[count:]


def _compute_distributions(samples: list[dict]) -> dict:
    total = len(samples)
    bucket_counts: dict[str, int] = defaultdict(int)
    intent_counts: dict[str, int] = defaultdict(int)
    module_counts: dict[str, int] = defaultdict(int)

    for sample in samples:
        coverage = sample.get("quality", {}).get("coverage", {})
        bucket = coverage.get("bucket") or "high"
        intent = coverage.get("intent") or "unknown"
        module_span = coverage.get("module_span") or "unknown"

        bucket_counts[bucket] += 1
        intent_counts[intent] += 1
        module_counts[module_span] += 1

    def ratios(counts: dict[str, int]) -> dict[str, float]:
        if total == 0:
            return {}
        return {key: round(value / total, 4) for key, value in counts.items()}

    return {
        "bucket_distribution": {
            "counts": dict(bucket_counts),
            "ratios": ratios(bucket_counts),
        },
        "intent_distribution": {
            "counts": dict(intent_counts),
            "ratios": ratios(intent_counts),
        },
        "module_span_distribution": {
            "counts": dict(module_counts),
            "ratios": ratios(module_counts),
        },
    }


def _sample_by_targets(
    samples: list[dict],
    targets: dict[str, float],
    seed: int,
    logger=None,
    scope: str | None = None,
) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    total = len(samples)
    normalized_targets, used_default = _normalize_targets(targets)
    if used_default and logger:
        scope_hint = f" ({scope})" if scope else ""
        logger.warning(
            "Coverage targets missing/zero%s; fallback to default 80/15/5. "
            "Check config path and coverage.targets.",
            scope_hint,
        )
    desired = _desired_counts(total, normalized_targets)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        bucket = (
            sample.get("quality", {})
            .get("coverage", {})
            .get("bucket", "high")
        )
        if bucket not in BUCKETS:
            bucket = "high"
        grouped[bucket].append(sample)

    selected: dict[str, list[dict]] = {}
    remaining: dict[str, list[dict]] = {}
    for bucket in BUCKETS:
        picks, rest = _pick_samples(rng, grouped.get(bucket, []).copy(), desired[bucket])
        selected[bucket] = picks
        remaining[bucket] = rest

    borrowed = defaultdict(lambda: defaultdict(int))
    deficits = {
        bucket: max(0, desired[bucket] - len(selected[bucket]))
        for bucket in BUCKETS
    }

    for bucket in ("hard", "mid"):
        deficit = deficits[bucket]
        if deficit <= 0:
            continue
        for fallback in FALLBACK_CHAIN[bucket]:
            if deficit <= 0:
                break
            available = remaining.get(fallback, [])
            if not available:
                continue
            take = min(deficit, len(available))
            selected[bucket].extend(available[:take])
            remaining[fallback] = available[take:]
            borrowed[bucket][fallback] += take
            deficit -= take
        deficits[bucket] = deficit

    final_samples = []
    final_counts = {}
    for bucket in BUCKETS:
        final_samples.extend(selected[bucket])
        final_counts[bucket] = len(selected[bucket])

    report = {
        "total": total,
        "targets": normalized_targets,
        "raw_targets": targets,
        "used_default_targets": used_default,
        "desired_counts": desired,
        "final_counts": final_counts,
        "deficits": deficits,
        "borrowed": {k: dict(v) for k, v in borrowed.items()},
    }
    report.update(_compute_distributions(final_samples))
    return final_samples, report


class CoverageSamplerStep(BaseStep):
    """Sample clean datasets by coverage targets."""

    @property
    def name(self) -> str:
        return "coverage_sampler"

    @property
    def display_name(self) -> str:
        return "Step 7: Coverage Sampling"

    def _sample_file(
        self,
        path: Path,
        targets: dict[str, float],
        seed: int,
        mode: str,
        min_sample_size: int,
    ) -> tuple[list[dict], dict]:
        if not path.exists():
            self.logger.info("Coverage sampling skipped, file not found: %s", path)
            return [], {"path": str(path), "skipped": True, "reason": "missing"}

        samples = read_jsonl(path)
        if not samples:
            self.logger.info("Coverage sampling skipped, empty file: %s", path)
            return [], {"path": str(path), "skipped": True, "reason": "empty"}

        normalized_targets, used_default = _normalize_targets(targets)

        if mode == "upstream":
            report = {
                "path": str(path),
                "skipped": True,
                "reason": "mode=upstream",
                "total": len(samples),
                "targets": normalized_targets,
                "raw_targets": targets,
                "used_default_targets": used_default,
            }
            report.update(_compute_distributions(samples))
            return samples, report

        if len(samples) < min_sample_size:
            report = {
                "path": str(path),
                "skipped": True,
                "reason": "below_min_sample_size",
                "min_sample_size": min_sample_size,
                "total": len(samples),
                "targets": normalized_targets,
                "raw_targets": targets,
                "used_default_targets": used_default,
            }
            report.update(_compute_distributions(samples))
            return samples, report

        sampled, report = _sample_by_targets(samples, targets, seed, self.logger, path.name)
        report["path"] = str(path)
        return sampled, report

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
                "coverage_report_json",
                self.paths.get("reports", "data/reports") / "coverage_report.json",
            )
        )

        seed = int(self.config.get("core.seed", 42))
        qa_cov = self.config.get("question_answer.coverage", {}) or {}
        design_cov = self.config.get("design_questions.coverage", {}) or {}

        qa_mode = qa_cov.get("mode", "hybrid")
        design_mode = design_cov.get("mode", "hybrid")

        qa_targets = qa_cov.get("targets", {})
        design_targets = design_cov.get("targets", {})
        qa_min_samples = int(qa_cov.get("min_sample_size", 30))
        design_min_samples = int(design_cov.get("min_sample_size", 30))

        qa_samples, qa_report = self._sample_file(
            qa_clean_path,
            qa_targets,
            seed,
            qa_mode,
            qa_min_samples,
        )
        if qa_samples and qa_mode != "upstream":
            write_jsonl(qa_clean_path, qa_samples)

        design_samples, design_report = self._sample_file(
            design_clean_path,
            design_targets,
            seed,
            design_mode,
            design_min_samples,
        )
        if design_samples and design_mode != "upstream":
            write_jsonl(design_clean_path, design_samples)

        report = {
            "qa": qa_report,
            "design": design_report,
        }
        write_json(report_path, report)

        return {
            "status": "success",
            "report_path": str(report_path),
            "qa_total": qa_report.get("total", 0),
            "design_total": design_report.get("total", 0),
        }
