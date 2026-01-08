from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.steps.secrets_scan import SecretsScanStep
from src.utils import read_jsonl, write_jsonl
from src.utils.schemas import sha256_text
from src.utils.validator import load_symbols_map, validate_dataset


class _Args:
    skip_safety = False


def _make_symbol(symbol_id: str, file_path: str, start_line: int = 1, end_line: int = 2) -> dict:
    source = "public class Demo { }"
    return {
        "symbol_id": symbol_id,
        "symbol_type": "class",
        "name": "Demo",
        "qualified_name": "Demo",
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "source": source,
        "doc": None,
        "annotations": [],
        "metadata": {},
        "repo_commit": "UNKNOWN_COMMIT",
        "source_hash": sha256_text(source),
    }


def _make_evidence_ref(symbol: dict, start_line: int | None = None, end_line: int | None = None) -> dict:
    return {
        "symbol_id": symbol["symbol_id"],
        "file_path": symbol["file_path"],
        "start_line": start_line or symbol["start_line"],
        "end_line": end_line or symbol["end_line"],
        "source_hash": symbol["source_hash"],
    }


def test_validator_rejects_invalid_evidence(tmp_path: Path) -> None:
    symbols_path = tmp_path / "symbols.jsonl"
    input_path = tmp_path / "qa_raw.jsonl"
    report_path = tmp_path / "qa_quality.json"
    rejected_path = tmp_path / "qa_validation_rejected.jsonl"
    clean_path = tmp_path / "qa_clean.jsonl"

    valid_symbol = _make_symbol(
        symbol_id="src/Demo.java:Demo:1",
        file_path="src/Demo.java",
    )
    write_jsonl(symbols_path, [valid_symbol])

    invalid_sample = {
        "scenario": "qa_rule",
        "instruction": "Force reject sample",
        "context": "irrelevant",
        "thought": {
            "observations": [],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": [
                {
                    "symbol_id": "INVALID_SYMBOL_ID",
                    "file_path": "invalid/path/DoesNotExist.java",
                    "start_line": 1,
                    "end_line": 1,
                    "source_hash": "deadbeef",
                }
            ],
        },
        "answer": "N/A",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(input_path, [invalid_sample])

    config = {"quality": {"trace_rules": {"require_non_empty": False}}}
    symbols_map = load_symbols_map(symbols_path)
    validate_dataset(input_path, symbols_map, report_path, rejected_path, clean_path, config)

    rejected = read_jsonl(rejected_path)
    assert rejected, "Expected rejected samples"
    errors = rejected[0]["quality"]["errors"]
    assert any(err["code"] == "EVIDENCE_SYMBOL_NOT_FOUND" for err in errors)


def test_design_warnings_written_to_clean(tmp_path: Path) -> None:
    symbols_path = tmp_path / "symbols.jsonl"
    input_path = tmp_path / "design_raw.jsonl"
    report_path = tmp_path / "design_quality.json"
    rejected_path = tmp_path / "design_validation_rejected.jsonl"
    clean_path = tmp_path / "design_clean.jsonl"

    symbol = _make_symbol(
        symbol_id="src/design/Demo.java:Demo:1",
        file_path="src/design/Demo.java",
    )
    write_jsonl(symbols_path, [symbol])

    sample = {
        "scenario": "arch_design",
        "instruction": "解释设计兼容性约束",
        "context": "context",
        "thought": {
            "observations": ["Uses v1 interface"],
            "inferences": ["Need to keep legacy path"],
            "assumptions": [],
            "evidence_refs": [_make_evidence_ref(symbol)],
        },
        "answer": "Answer",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(input_path, [sample])

    config = {
        "quality": {"trace_rules": {"require_non_empty": False}},
        "design_questions": {"min_evidence_refs": 2, "require_layer_coverage": True},
    }
    symbols_map = load_symbols_map(symbols_path)
    validate_dataset(input_path, symbols_map, report_path, rejected_path, clean_path, config)

    clean = read_jsonl(clean_path)
    assert clean, "Expected clean samples"
    warnings = clean[0]["quality"]["warnings"]
    warning_codes = {warn["code"] for warn in warnings}
    assert "DESIGN_EVIDENCE_TOO_FEW" in warning_codes
    assert "DESIGN_LAYER_COVERAGE_LOW" in warning_codes


def test_trace_mode_rejects_on_empty_trace(tmp_path: Path) -> None:
    symbols_path = tmp_path / "symbols.jsonl"
    input_path = tmp_path / "qa_raw.jsonl"
    report_path = tmp_path / "qa_quality.json"
    rejected_path = tmp_path / "qa_validation_rejected.jsonl"
    clean_path = tmp_path / "qa_clean.jsonl"

    symbol = _make_symbol(
        symbol_id="src/trace/Demo.java:Demo:1",
        file_path="src/trace/Demo.java",
    )
    write_jsonl(symbols_path, [symbol])

    sample = {
        "scenario": "qa_rule",
        "instruction": "How does this work?",
        "context": "context",
        "thought": {
            "observations": [],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": [_make_evidence_ref(symbol)],
        },
        "answer": "Answer",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(input_path, [sample])

    config = {
        "quality": {
            "trace_rules": {
                "mode": "reject",
                "require_non_empty": True,
                "require_evidence_alignment": True,
            }
        }
    }
    symbols_map = load_symbols_map(symbols_path)
    validate_dataset(input_path, symbols_map, report_path, rejected_path, clean_path, config)

    rejected = read_jsonl(rejected_path)
    assert rejected, "Expected rejected samples"
    checks = rejected[0]["quality"]["checks"]
    assert checks["trace"] == "warn"


def test_trace_evidence_anchor_warns_for_negative(tmp_path: Path) -> None:
    symbols_path = tmp_path / "symbols.jsonl"
    input_path = tmp_path / "qa_raw.jsonl"
    report_path = tmp_path / "qa_quality.json"
    rejected_path = tmp_path / "qa_validation_rejected.jsonl"
    clean_path = tmp_path / "qa_clean.jsonl"

    symbol = _make_symbol(
        symbol_id="src/trace_anchor/Demo.java:Demo:1",
        file_path="src/trace_anchor/Demo.java",
    )
    write_jsonl(symbols_path, [symbol])

    sample = {
        "scenario": "qa_rule",
        "instruction": "Need negative sample",
        "context": "context",
        "thought": {
            "observations": ["Missing evidence"],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": [],
        },
        "answer": "Insufficient evidence.",
        "repo_commit": "UNKNOWN_COMMIT",
        "quality": {"coverage": {"polarity": "negative"}},
    }
    write_jsonl(input_path, [sample])

    config = {
        "quality": {
            "allow_negative_without_evidence": True,
            "trace_rules": {
                "mode": "warning",
                "require_non_empty": False,
                "require_evidence_alignment": False,
                "require_evidence_anchor": True,
            },
        }
    }
    symbols_map = load_symbols_map(symbols_path)
    validate_dataset(input_path, symbols_map, report_path, rejected_path, clean_path, config)

    clean = read_jsonl(clean_path)
    assert clean, "Expected clean samples"
    warning_codes = {warn["code"] for warn in clean[0]["quality"]["warnings"]}
    assert "TRACE_EVIDENCE_ANCHOR" in warning_codes


def test_trace_answer_alignment_warns(tmp_path: Path) -> None:
    symbols_path = tmp_path / "symbols.jsonl"
    input_path = tmp_path / "qa_raw.jsonl"
    report_path = tmp_path / "qa_quality.json"
    rejected_path = tmp_path / "qa_validation_rejected.jsonl"
    clean_path = tmp_path / "qa_clean.jsonl"

    symbol = _make_symbol(
        symbol_id="src/trace_align/Demo.java:Demo:1",
        file_path="src/trace_align/Demo.java",
    )
    write_jsonl(symbols_path, [symbol])

    sample = {
        "scenario": "qa_rule",
        "instruction": "Answer alignment check",
        "context": "context",
        "thought": {
            "observations": ["Uses CacheManager"],
            "inferences": ["Cache is initialized"],
            "assumptions": [],
            "evidence_refs": [_make_evidence_ref(symbol)],
        },
        "answer": "Requires audit logging before execution.",
        "repo_commit": "UNKNOWN_COMMIT",
    }
    write_jsonl(input_path, [sample])

    config = {
        "quality": {
            "trace_rules": {
                "mode": "warning",
                "require_non_empty": False,
                "require_evidence_alignment": False,
                "require_answer_alignment": True,
            }
        }
    }
    symbols_map = load_symbols_map(symbols_path)
    validate_dataset(input_path, symbols_map, report_path, rejected_path, clean_path, config)

    clean = read_jsonl(clean_path)
    assert clean, "Expected clean samples"
    warning_codes = {warn["code"] for warn in clean[0]["quality"]["warnings"]}
    assert "TRACE_ANSWER_ALIGNMENT" in warning_codes


def test_blacklist_modes(tmp_path: Path) -> None:
    sample = {
        "scenario": "qa_rule",
        "instruction": "Test",
        "context": "作为人工智能，这是不该出现的内容。",
        "answer": "OK",
    }

    for mode, expect_removed, expect_sanitized in [
        ("drop", True, False),
        ("keep", False, False),
        ("sanitize", False, True),
    ]:
        run_dir = tmp_path / mode
        run_dir.mkdir()
        input_path = run_dir / "all_dedup.jsonl"
        report_path = run_dir / "secrets_dropped.jsonl"
        write_jsonl(input_path, [sample])

        config = {
            "safety": {
                "mode": mode,
                "blacklist_keywords": ["作为人工智能"],
            }
        }
        paths = {
            "all_dedup_jsonl": input_path,
            "secrets_dropped_jsonl": report_path,
        }

        step = SecretsScanStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
        step.execute()

        remaining = read_jsonl(input_path)
        if expect_removed:
            assert not remaining
        else:
            assert remaining
            if expect_sanitized:
                assert "[REDACTED]" in remaining[0]["context"]

        flagged = read_jsonl(report_path)
        assert flagged
        assert flagged[0]["action"] == mode


def _run() -> None:
    tests = [
        test_validator_rejects_invalid_evidence,
        test_design_warnings_written_to_clean,
        test_trace_mode_rejects_on_empty_trace,
        test_trace_evidence_anchor_warns_for_negative,
        test_trace_answer_alignment_warns,
        test_blacklist_modes,
    ]
    for test in tests:
        test()
    print(f"OK: {len(tests)} tests passed")


if __name__ == "__main__":
    _run()
