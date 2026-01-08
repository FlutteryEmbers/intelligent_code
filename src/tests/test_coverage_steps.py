from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.steps.coverage_sampler import CoverageSamplerStep
from src.pipeline.steps.coverage_tagger import CoverageTaggerStep
from src.utils import read_json, read_jsonl, write_jsonl


class _Args:
    skip_safety = False


def _sample_with_bucket(bucket: str, intent: str = "how_to") -> dict:
    return {
        "scenario": "qa_rule",
        "instruction": f"{bucket} question",
        "context": "context",
        "thought": {"observations": [], "inferences": [], "assumptions": [], "evidence_refs": []},
        "answer": "answer",
        "repo_commit": "UNKNOWN_COMMIT",
        "quality": {"coverage": {"bucket": bucket, "intent": intent, "module_span": "single"}},
    }


def test_coverage_tagger_infers_labels(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa_clean.jsonl"
    design_path = tmp_path / "design_clean.jsonl"

    qa_sample = {
        "scenario": "qa_rule",
        "instruction": "如何配置开关",
        "context": "context",
        "thought": {
            "observations": [],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": [
                {"file_path": "module_a/Foo.java"},
                {"file_path": "module_b/Bar.java"},
            ],
        },
        "answer": "answer",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    design_sample = {
        "scenario": "arch_design",
        "instruction": "兼容性策略说明",
        "context": "context",
        "thought": {"observations": [], "inferences": [], "assumptions": [], "evidence_refs": []},
        "answer": "answer",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(qa_path, [qa_sample])
    write_jsonl(design_path, [design_sample])

    config = {
        "question_answer.coverage": {
            "labeler": "rule",
            "evidence_refs": {"mode": "assist", "mid_min": 2, "hard_min": 3},
        },
        "design_questions.coverage": {
            "labeler": "rule",
            "evidence_refs": {"mode": "assist", "mid_min": 2, "hard_min": 3},
        },
        "artifacts": {
            "qa_clean_jsonl": str(qa_path),
            "design_clean_jsonl": str(design_path),
        },
    }
    paths = {
        "qa_clean_jsonl": qa_path,
        "design_clean_jsonl": design_path,
    }
    step = CoverageTaggerStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    step.execute()

    qa_out = read_jsonl(qa_path)[0]["quality"]["coverage"]
    assert qa_out["intent"] == "config"
    assert qa_out["module_span"] == "multi"
    assert qa_out["bucket"] == "mid"

    design_out = read_jsonl(design_path)[0]["quality"]["coverage"]
    assert design_out["intent"] == "compatibility"
    assert design_out["bucket"] == "hard"


def test_coverage_tagger_uses_evidence_refs_assist(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa_clean.jsonl"

    qa_sample = {
        "scenario": "qa_rule",
        "instruction": "如何使用这个功能",
        "context": "context",
        "thought": {
            "observations": [],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": [
                {"file_path": "module_a/Foo.java"},
                {"file_path": "module_a/Bar.java"},
            ],
        },
        "answer": "answer",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(qa_path, [qa_sample])

    config = {
        "question_answer.coverage": {
            "labeler": "rule",
            "evidence_refs": {"mode": "assist", "mid_min": 2, "hard_min": 3},
        },
        "design_questions.coverage": {"labeler": "rule"},
        "artifacts": {"qa_clean_jsonl": str(qa_path)},
    }
    paths = {"qa_clean_jsonl": qa_path}
    step = CoverageTaggerStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    step.execute()

    coverage = read_jsonl(qa_path)[0]["quality"]["coverage"]
    assert coverage["module_span"] == "single"
    assert coverage["bucket"] == "mid"


def test_coverage_tagger_evidence_refs_assist_no_downgrade(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa_clean.jsonl"

    qa_sample = {
        "scenario": "qa_rule",
        "instruction": "兼容性策略说明",
        "context": "context",
        "thought": {
            "observations": [],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": [
                {"file_path": "module_a/Foo.java"},
            ],
        },
        "answer": "answer",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(qa_path, [qa_sample])

    config = {
        "question_answer.coverage": {
            "labeler": "rule",
            "evidence_refs": {"mode": "assist", "mid_min": 2, "hard_min": 3},
        },
        "artifacts": {"qa_clean_jsonl": str(qa_path)},
    }
    paths = {"qa_clean_jsonl": qa_path}
    step = CoverageTaggerStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    step.execute()

    coverage = read_jsonl(qa_path)[0]["quality"]["coverage"]
    assert coverage["intent"] == "compatibility"
    assert coverage["bucket"] == "hard"

def test_coverage_sampler_applies_targets_and_writes_report(tmp_path: Path) -> None:
    qa_path = tmp_path / "qa_clean.jsonl"
    design_path = tmp_path / "design_clean.jsonl"
    report_path = tmp_path / "coverage_report.json"

    samples = (
        [_sample_with_bucket("high") for _ in range(10)]
        + [_sample_with_bucket("mid") for _ in range(6)]
        + [_sample_with_bucket("hard") for _ in range(4)]
    )
    write_jsonl(qa_path, samples)
    write_jsonl(design_path, [_sample_with_bucket("high") for _ in range(5)])

    config = {
        "core.seed": 7,
        "question_answer.coverage": {
            "mode": "hybrid",
            "targets": {"high": 0.5, "mid": 0.3, "hard": 0.2},
            "min_sample_size": 0,
        },
        "design_questions.coverage": {
            "mode": "upstream",
            "targets": {"high": 1.0, "mid": 0.0, "hard": 0.0},
            "min_sample_size": 0,
        },
        "artifacts": {
            "qa_clean_jsonl": str(qa_path),
            "design_clean_jsonl": str(design_path),
            "coverage_report_json": str(report_path),
        },
    }
    paths = {
        "qa_clean_jsonl": qa_path,
        "design_clean_jsonl": design_path,
        "reports": tmp_path,
    }
    step = CoverageSamplerStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    step.execute()

    sampled = read_jsonl(qa_path)
    buckets = Counter(sample["quality"]["coverage"]["bucket"] for sample in sampled)
    assert buckets["high"] == 10
    assert buckets["mid"] == 6
    assert buckets["hard"] == 4

    report = read_json(report_path)
    assert report
    assert "qa" in report and "design" in report
    assert "bucket_distribution" in report["qa"]
