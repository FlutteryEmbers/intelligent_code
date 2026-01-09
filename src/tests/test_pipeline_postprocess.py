from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.steps.deduplication import DeduplicationStep
from src.pipeline.steps.merge import MergeStep
from src.pipeline.steps.split import SplitStep
from src.utils.io.file_ops import read_jsonl, write_jsonl
from src.utils.core.schemas import sha256_text


class _Args:
    skip_qa = False
    skip_llm = False
    skip_dedup = False


def _make_symbol(symbol_id: str, file_path: str) -> dict:
    source = "public class Demo { }"
    return {
        "symbol_id": symbol_id,
        "symbol_type": "class",
        "name": "Demo",
        "qualified_name": "com.example.Demo",
        "file_path": file_path,
        "start_line": 1,
        "end_line": 2,
        "source": source,
        "doc": None,
        "annotations": [],
        "metadata": {},
        "repo_commit": "UNKNOWN_COMMIT",
        "source_hash": sha256_text(source),
    }


def _make_sample(scenario: str, instruction: str, answer: str, symbol: dict | None = None) -> dict:
    evidence_refs = []
    if symbol:
        evidence_refs = [
            {
                "symbol_id": symbol["symbol_id"],
                "file_path": symbol["file_path"],
                "start_line": symbol["start_line"],
                "end_line": symbol["end_line"],
                "source_hash": symbol["source_hash"],
            }
        ]
    return {
        "scenario": scenario,
        "instruction": instruction,
        "context": "context",
        "thought": {
            "observations": [],
            "inferences": [],
            "assumptions": [],
            "evidence_refs": evidence_refs,
        },
        "answer": answer,
        "repo_commit": "UNKNOWN_COMMIT",
    }


def test_merge_prefers_clean_outputs(tmp_path: Path) -> None:
    qa_clean = tmp_path / "qa_clean.jsonl"
    design_clean = tmp_path / "design_clean.jsonl"
    all_raw = tmp_path / "all_raw.jsonl"
    qa_raw = tmp_path / "qa_raw.jsonl"
    design_raw = tmp_path / "design_raw.jsonl"

    write_jsonl(qa_clean, [_make_sample("qa_rule", "Q1", "A1")])
    write_jsonl(design_clean, [_make_sample("arch_design", "D1", "A2")])
    write_jsonl(qa_raw, [_make_sample("qa_rule", "Q-raw", "A-raw")])
    write_jsonl(design_raw, [_make_sample("arch_design", "D-raw", "A-raw")])

    config = {
        "quality": {"gate_mode": "report", "write_clean": True},
        "artifacts": {
            "qa_clean_jsonl": str(qa_clean),
            "design_clean_jsonl": str(design_clean),
        },
    }
    paths = {
        "qa_raw_jsonl": qa_raw,
        "design_raw_jsonl": design_raw,
        "all_raw_jsonl": all_raw,
        "qa_clean_jsonl": qa_clean,
        "design_clean_jsonl": design_clean,
    }
    step = MergeStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    step.execute()

    merged = read_jsonl(all_raw)
    scenarios = {sample["scenario"] for sample in merged}
    assert len(merged) == 2
    assert scenarios == {"qa_rule", "arch_design"}


def test_merge_gate_mode_requires_clean(tmp_path: Path) -> None:
    qa_raw = tmp_path / "qa_raw.jsonl"
    design_raw = tmp_path / "design_raw.jsonl"
    qa_clean = tmp_path / "qa_clean.jsonl"
    design_clean = tmp_path / "design_clean.jsonl"

    write_jsonl(qa_raw, [_make_sample("qa_rule", "Q1", "A1")])
    write_jsonl(design_raw, [_make_sample("arch_design", "D1", "A2")])

    config = {
        "quality": {"gate_mode": "gate", "write_clean": True},
        "artifacts": {
            "qa_clean_jsonl": str(qa_clean),
            "design_clean_jsonl": str(design_clean),
        },
    }
    paths = {
        "qa_raw_jsonl": qa_raw,
        "design_raw_jsonl": design_raw,
        "qa_clean_jsonl": qa_clean,
        "design_clean_jsonl": design_clean,
        "all_raw_jsonl": tmp_path / "all_raw.jsonl",
    }
    step = MergeStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")

    with pytest.raises(FileNotFoundError):
        step.execute()


def test_deduplication_drops_duplicates(tmp_path: Path) -> None:
    all_raw = tmp_path / "all_raw.jsonl"
    all_dedup = tmp_path / "all_dedup.jsonl"
    mapping = tmp_path / "dedup_mapping.json"

    samples = [
        _make_sample("qa_rule", "Same question", "Same answer"),
        _make_sample("qa_rule", "Same question", "Same answer"),
        _make_sample("qa_rule", "Different question", "Different answer"),
    ]
    write_jsonl(all_raw, samples)

    config = {"dedup": {"simhash_bits": 64, "max_hamming": 0}, "generation": {"seed": 1}}
    paths = {
        "all_raw_jsonl": all_raw,
        "all_dedup_jsonl": all_dedup,
        "dedup_mapping_json": mapping,
    }
    step = DeduplicationStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    step.execute()

    deduped = read_jsonl(all_dedup)
    assert len(deduped) == 2


def test_split_step_writes_outputs(tmp_path: Path) -> None:
    all_dedup = tmp_path / "all_dedup.jsonl"
    symbols = tmp_path / "symbols.jsonl"

    symbol = _make_symbol("src/Demo.java:Demo:1", "src/Demo.java")
    write_jsonl(symbols, [symbol])

    samples = [
        _make_sample("qa_rule", "Q1", "A1", symbol),
        _make_sample("qa_rule", "Q2", "A2", symbol),
        _make_sample("arch_design", "D1", "A3", symbol),
    ]
    write_jsonl(all_dedup, samples)

    paths = {
        "all_dedup_jsonl": all_dedup,
        "symbols_jsonl": symbols,
        "train_jsonl": tmp_path / "train.jsonl",
        "val_jsonl": tmp_path / "val.jsonl",
        "test_jsonl": tmp_path / "test.jsonl",
        "qa_train_jsonl": tmp_path / "qa_train.jsonl",
        "qa_val_jsonl": tmp_path / "qa_val.jsonl",
        "qa_test_jsonl": tmp_path / "qa_test.jsonl",
        "design_train_jsonl": tmp_path / "design_train.jsonl",
        "design_val_jsonl": tmp_path / "design_val.jsonl",
        "design_test_jsonl": tmp_path / "design_test.jsonl",
    }
    config = {"split": {"train_ratio": 0.8, "val_ratio": 0.1, "test_ratio": 0.1}, "generation": {"seed": 1}}
    step = SplitStep(config, _Args(), paths, repo_commit="UNKNOWN_COMMIT")
    result = step.execute()

    total = result["train_count"] + result["val_count"] + result["test_count"]
    assert total == len(samples)
    assert paths["train_jsonl"].exists()
    assert paths["qa_train_jsonl"].exists()
    assert paths["design_train_jsonl"].exists()
