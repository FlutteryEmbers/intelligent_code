"""
Coverage sampling step.
"""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from src.pipeline.base_step import BaseStep
from src.utils.io.file_ops import read_jsonl, write_jsonl, write_json
from src.utils.data.coverage import (
    BUCKETS,
    DEFAULT_TARGETS,
    FALLBACK_CHAIN,
    normalize_targets,
    desired_counts,
    compute_multi_distributions,
)


def _pick_samples(rng: random.Random, samples: list[dict], count: int) -> tuple[list[dict], list[dict]]:
    """Pick samples from list and return (selected, remaining)."""
    if count <= 0:
        return [], samples
    if count >= len(samples):
        return samples, []
    rng.shuffle(samples)
    return samples[:count], samples[count:]


def _sample_by_targets(
    samples: list[dict],
    targets: dict[str, float],
    seed: int,
    logger=None,
    scope: str | None = None,
    negative_ratio: float | None = None,
) -> tuple[list[dict], dict]:
    """Sample by coverage targets with optional negative ratio."""
    rng = random.Random(seed)
    total = len(samples)
    normalized_targets, used_default = normalize_targets(targets)
    if used_default and logger:
        scope_hint = f" ({scope})" if scope else ""
        logger.warning(
            "Coverage targets missing/zero%s; fallback to default 80/15/5. "
            "Check config path and coverage.targets.",
            scope_hint,
        )
    desired = desired_counts(total, normalized_targets)

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
    polarity_deficits: dict[str, int] = {}
    for bucket in BUCKETS:
        bucket_samples = grouped.get(bucket, []).copy()
        if negative_ratio is None:
            picks, rest = _pick_samples(rng, bucket_samples, desired[bucket])
            selected[bucket] = picks
            remaining[bucket] = rest
            continue

        negatives = [
            sample for sample in bucket_samples
            if sample.get("quality", {}).get("coverage", {}).get("polarity") == "negative"
        ]
        positives = [sample for sample in bucket_samples if sample not in negatives]
        desired_neg = int(round(desired[bucket] * float(negative_ratio)))
        desired_pos = max(0, desired[bucket] - desired_neg)

        neg_picks, neg_rest = _pick_samples(rng, negatives, desired_neg)
        pos_picks, pos_rest = _pick_samples(rng, positives, desired_pos)

        picks = neg_picks + pos_picks
        rest_pool = neg_rest + pos_rest

        remaining_needed = max(0, desired[bucket] - len(picks))
        if remaining_needed:
            extra_picks, extra_rest = _pick_samples(rng, rest_pool, remaining_needed)
            picks.extend(extra_picks)
            rest_pool = extra_rest

        selected[bucket] = picks
        remaining[bucket] = rest_pool
        polarity_deficits[bucket] = max(0, desired_neg - len(neg_picks))

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
        "negative_ratio": negative_ratio,
        "negative_deficits": polarity_deficits,
    }
    report.update(compute_multi_distributions(final_samples))
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
        negative_ratio: float | None,
    ) -> tuple[list[dict], dict]:
        if not path.exists():
            self.logger.info("Coverage sampling skipped, file not found: %s", path)
            return [], {"path": str(path), "skipped": True, "reason": "missing"}

        samples = read_jsonl(path)
        if not samples:
            self.logger.info("Coverage sampling skipped, empty file: %s", path)
            return [], {"path": str(path), "skipped": True, "reason": "empty"}

        normalized_targets, used_default = normalize_targets(targets)

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
            report.update(compute_multi_distributions(samples))
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
            report.update(compute_multi_distributions(samples))
            return samples, report

        sampled, report = _sample_by_targets(
            samples,
            targets,
            seed,
            self.logger,
            path.name,
            negative_ratio=negative_ratio,
        )
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
        qa_negative_ratio = qa_cov.get("negative_ratio")
        design_negative_ratio = design_cov.get("negative_ratio")

        qa_samples, qa_report = self._sample_file(
            qa_clean_path,
            qa_targets,
            seed,
            qa_mode,
            qa_min_samples,
            qa_negative_ratio,
        )
        if qa_samples and qa_mode != "upstream":
            write_jsonl(qa_clean_path, qa_samples)

        design_samples, design_report = self._sample_file(
            design_clean_path,
            design_targets,
            seed,
            design_mode,
            design_min_samples,
            design_negative_ratio,
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
