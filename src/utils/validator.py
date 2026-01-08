"""
Dataset quality validation utilities.
Provides sample validation and dataset quality gates.
"""
import json
from pathlib import Path
from typing import Any
from collections import Counter

from .schemas import CodeSymbol, TrainingSample, EvidenceRef
from .io import read_jsonl, write_json, append_jsonl


def normalize_path_separators(path: str) -> str:
    """
    Normalize path separators to forward slashes for cross-platform compatibility.
    Converts Windows backslashes (\\) to Unix forward slashes (/).
    
    Args:
        path: Path string with any separator type
        
    Returns:
        Path string with normalized forward slashes
    """
    return path.replace('\\', '/')


def load_symbols_map(symbols_jsonl: Path | str) -> dict[str, CodeSymbol]:
    """
    Load symbols from JSONL and build symbol_id -> CodeSymbol mapping.
    Normalizes symbol_ids to use forward slashes for cross-platform compatibility.
    
    Args:
        symbols_jsonl: Path to symbols.jsonl file
        
    Returns:
        Dict mapping normalized symbol_id to CodeSymbol
    """
    symbols_jsonl = Path(symbols_jsonl)
    symbols_map = {}
    
    raw_lines = read_jsonl(symbols_jsonl)
    
    for idx, raw_obj in enumerate(raw_lines, 1):
        try:
            symbol = CodeSymbol.model_validate(raw_obj)
            # Normalize symbol_id for cross-platform compatibility
            normalized_id = normalize_path_separators(symbol.symbol_id)
            symbols_map[normalized_id] = symbol
        except Exception as e:
            print(f"Warning: Failed to parse symbol at line {idx}: {e}")
            continue
    
    print(f"Loaded {len(symbols_map)} symbols from {symbols_jsonl}")
    return symbols_map


def _quality_issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _set_check(checks: dict[str, str], key: str, status: str) -> None:
    current = checks.get(key, "pass")
    if current == "fail":
        return
    if current == "warn" and status == "pass":
        return
    checks[key] = status


def validate_sample_obj(
    sample: TrainingSample,
    symbols_map: dict[str, CodeSymbol],
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Validate a single TrainingSample against symbols map.

    Returns a quality dict with gate results.
    """
    config = config or {}
    quality_cfg = config.get("quality", {})
    design_cfg = config.get("design_questions", {})
    trace_cfg = quality_cfg.get("trace_rules", {}) if isinstance(quality_cfg, dict) else {}

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checks = {
        "schema": "pass",
        "evidence": "pass",
        "commit": "pass",
        "length": "pass",
        "scenario_rules": "pass",
        "trace": "pass",
    }

    evidence_refs = []
    trace = sample.thought
    if trace:
        evidence_refs = trace.evidence_refs or []

    if not evidence_refs:
        allow_negative_no_evidence = bool(quality_cfg.get("allow_negative_without_evidence", False))
        is_negative = (
            sample.quality.get("coverage", {}).get("polarity") == "negative"
            if isinstance(sample.quality, dict)
            else False
        )
        if allow_negative_no_evidence and is_negative:
            warnings.append(
                _quality_issue(
                    "EVIDENCE_MISSING_NEGATIVE",
                    "Missing thought.evidence_refs for negative sample",
                )
            )
            _set_check(checks, "evidence", "warn")
        else:
            errors.append(_quality_issue("EVIDENCE_MISSING", "Missing thought.evidence_refs"))
            _set_check(checks, "evidence", "fail")
    else:
        for idx, ref in enumerate(evidence_refs):
            ref_id = f"evidence_refs[{idx}]"
            normalized_symbol_id = normalize_path_separators(ref.symbol_id)
            if normalized_symbol_id not in symbols_map:
                errors.append(
                    _quality_issue(
                        "EVIDENCE_SYMBOL_NOT_FOUND",
                        f"{ref_id}: symbol_id '{ref.symbol_id}' not found in symbols map",
                    )
                )
                _set_check(checks, "evidence", "fail")
                continue

            symbol = symbols_map[normalized_symbol_id]

            if ref.source_hash != symbol.source_hash:
                errors.append(
                    _quality_issue(
                        "EVIDENCE_SOURCE_HASH_MISMATCH",
                        f"{ref_id}: source_hash mismatch (expected {symbol.source_hash[:8]}..., "
                        f"got {ref.source_hash[:8]}...)",
                    )
                )
                _set_check(checks, "evidence", "fail")

            if ref.start_line < 1 or ref.end_line < ref.start_line:
                errors.append(
                    _quality_issue(
                        "EVIDENCE_LINE_RANGE_INVALID",
                        f"{ref_id}: invalid line range [{ref.start_line}, {ref.end_line}]",
                    )
                )
                _set_check(checks, "evidence", "fail")

            if ref.end_line - ref.start_line > 500:
                warnings.append(
                    _quality_issue(
                        "EVIDENCE_RANGE_LARGE",
                        f"{ref_id}: suspiciously large line range ({ref.end_line - ref.start_line} lines)",
                    )
                )
                _set_check(checks, "evidence", "warn")

            normalized_ref_path = normalize_path_separators(ref.file_path)
            normalized_symbol_path = normalize_path_separators(symbol.file_path)
            if normalized_ref_path != normalized_symbol_path:
                errors.append(
                    _quality_issue(
                        "EVIDENCE_FILE_PATH_MISMATCH",
                        f"{ref_id}: file_path mismatch (expected {symbol.file_path}, got {ref.file_path})",
                    )
                )
                _set_check(checks, "evidence", "fail")

            if sample.repo_commit != "UNKNOWN_COMMIT" and symbol.repo_commit != "UNKNOWN_COMMIT":
                if sample.repo_commit != symbol.repo_commit:
                    warnings.append(
                        _quality_issue(
                            "COMMIT_MISMATCH",
                            f"{ref_id}: repo_commit mismatch "
                            f"(sample: {sample.repo_commit[:8]}..., symbol: {symbol.repo_commit[:8]}...)",
                        )
                    )
                    _set_check(checks, "commit", "warn")

    instruction_len = len(sample.instruction or "")
    answer_len = len(sample.answer or "")
    min_instruction = int(quality_cfg.get("min_instruction_length", 0))
    min_answer = int(quality_cfg.get("min_answer_length", 0))
    max_answer = int(quality_cfg.get("max_answer_length", 0))

    if min_instruction and instruction_len < min_instruction:
        warnings.append(
            _quality_issue(
                "INSTRUCTION_TOO_SHORT",
                f"instruction length {instruction_len} < min {min_instruction}",
            )
        )
        _set_check(checks, "length", "warn")

    if min_answer and answer_len < min_answer:
        warnings.append(
            _quality_issue(
                "ANSWER_TOO_SHORT",
                f"answer length {answer_len} < min {min_answer}",
            )
        )
        _set_check(checks, "length", "warn")

    if max_answer and answer_len > max_answer:
        warnings.append(
            _quality_issue(
                "ANSWER_TOO_LONG",
                f"answer length {answer_len} > max {max_answer}",
            )
        )
        _set_check(checks, "length", "warn")

    if sample.scenario == "arch_design":
        min_evidence_refs = int(design_cfg.get("min_evidence_refs", 2))
        if evidence_refs and len(evidence_refs) < min_evidence_refs:
            warnings.append(
                _quality_issue(
                    "DESIGN_EVIDENCE_TOO_FEW",
                    f"evidence_refs {len(evidence_refs)} < min {min_evidence_refs}",
                )
            )
            _set_check(checks, "scenario_rules", "warn")

        if design_cfg.get("require_layer_coverage", False) and evidence_refs:
            top_levels = {
                normalize_path_separators(ref.file_path).split("/")[0]
                for ref in evidence_refs
                if ref.file_path
            }
            if len(top_levels) < 2:
                warnings.append(
                    _quality_issue(
                        "DESIGN_LAYER_COVERAGE_LOW",
                        "evidence_refs lack multi-layer coverage",
                    )
                )
                _set_check(checks, "scenario_rules", "warn")
    else:
        if evidence_refs and len(evidence_refs) < 1:
            warnings.append(
                _quality_issue(
                    "QA_EVIDENCE_TOO_FEW",
                    "evidence_refs < 1",
                )
            )
            _set_check(checks, "scenario_rules", "warn")

    trace_mode = trace_cfg.get("mode", "warning")
    trace_scope = trace_cfg.get("scope", "all")
    require_evidence_refs = bool(trace_cfg.get("require_evidence_refs", False))

    trace_enabled = trace_scope == "all" or (
        trace_scope == "arch_design" and sample.scenario == "arch_design"
    )
    if trace_enabled and (not require_evidence_refs or evidence_refs):
        observations = trace.observations if trace else []
        inferences = trace.inferences if trace else []
        assumptions = trace.assumptions if trace else []

        if trace_cfg.get("require_non_empty", True):
            if not observations and not inferences:
                warnings.append(
                    _quality_issue(
                        "TRACE_EMPTY",
                        "observations and inferences are both empty",
                    )
                )
                _set_check(checks, "trace", "warn")

        if trace_cfg.get("require_evidence_alignment", True):
            if evidence_refs and (not observations and not inferences):
                warnings.append(
                    _quality_issue(
                        "TRACE_EVIDENCE_ALIGNMENT",
                        "evidence_refs present but trace steps are empty",
                    )
                )
                _set_check(checks, "trace", "warn")

        min_observations = trace_cfg.get("min_observations", 0)
        min_inferences = trace_cfg.get("min_inferences", 0)
        if len(observations) < min_observations:
            warnings.append(
                _quality_issue(
                    "TRACE_MIN_OBSERVATIONS",
                    f"observations {len(observations)} < min {min_observations}",
                )
            )
            _set_check(checks, "trace", "warn")
        if len(inferences) < min_inferences:
            warnings.append(
                _quality_issue(
                    "TRACE_MIN_INFERENCES",
                    f"inferences {len(inferences)} < min {min_inferences}",
                )
            )
            _set_check(checks, "trace", "warn")

        max_observations = trace_cfg.get("max_observations")
        max_inferences = trace_cfg.get("max_inferences")
        max_assumptions = trace_cfg.get("max_assumptions")
        if max_observations is not None and len(observations) > max_observations:
            warnings.append(
                _quality_issue(
                    "TRACE_MAX_OBSERVATIONS",
                    f"observations {len(observations)} > max {max_observations}",
                )
            )
            _set_check(checks, "trace", "warn")
        if max_inferences is not None and len(inferences) > max_inferences:
            warnings.append(
                _quality_issue(
                    "TRACE_MAX_INFERENCES",
                    f"inferences {len(inferences)} > max {max_inferences}",
                )
            )
            _set_check(checks, "trace", "warn")
        if max_assumptions is not None and len(assumptions) > max_assumptions:
            warnings.append(
                _quality_issue(
                    "TRACE_MAX_ASSUMPTIONS",
                    f"assumptions {len(assumptions)} > max {max_assumptions}",
                )
            )
            _set_check(checks, "trace", "warn")

    fail_on_warnings = bool(quality_cfg.get("fail_on_warnings", False))
    trace_is_error = trace_mode == "reject" and checks.get("trace") == "warn"
    passed = (
        not errors
        and (not warnings or not fail_on_warnings)
        and checks["evidence"] != "fail"
        and not trace_is_error
    )

    return {
        "gate_version": "v1",
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "stats": {
            "context_chars": len(sample.context or ""),
            "answer_chars": answer_len,
            "evidence_refs": len(evidence_refs),
        },
    }


def validate_dataset(
    input_jsonl: Path | str,
    symbols_map: dict[str, CodeSymbol],
    report_path: Path | str,
    rejected_path: Path | str,
    clean_path: Path | str | None = None,
    config: dict | None = None,
) -> None:
    """
    Validate entire dataset and generate quality report.
    
    Args:
        input_jsonl: Path to input JSONL file with TrainingSample objects
        symbols_map: symbol_id -> CodeSymbol mapping
        report_path: Path to output JSON report
        rejected_path: Path to output rejected samples JSONL
    """
    input_jsonl = Path(input_jsonl)
    report_path = Path(report_path)
    rejected_path = Path(rejected_path)
    clean_path = Path(clean_path) if clean_path else None
    config = config or {}
    quality_cfg = config.get("quality", {})
    write_clean = bool(quality_cfg.get("write_clean", True))
    
    # Statistics
    total = 0
    passed = 0
    failed = 0
    error_counter = Counter()
    warning_counter = Counter()
    trace_warning_samples = 0
    
    # Ensure rejected/clean files are empty
    if rejected_path.exists():
        rejected_path.unlink()
    if clean_path and clean_path.exists() and write_clean:
        clean_path.unlink()
    
    # Read and validate each sample
    raw_lines = read_jsonl(input_jsonl)
    
    for idx, raw_obj in enumerate(raw_lines, 1):
        total += 1
        
        # Try to parse as TrainingSample
        try:
            sample = TrainingSample.model_validate(raw_obj)
            schema_ok = True
        except Exception as e:
            # Schema validation failed
            schema_ok = False
            error_msg = f"Schema validation failed: {str(e)}"
            error_counter["SCHEMA_INVALID"] += 1
            quality = {
                "gate_version": "v1",
                "passed": False,
                "errors": [_quality_issue("SCHEMA_INVALID", error_msg)],
                "warnings": [],
                "checks": {
                    "schema": "fail",
                    "evidence": "fail",
                    "commit": "pass",
                    "length": "pass",
                    "scenario_rules": "pass",
                },
                "stats": {},
            }
            
            # Write to rejected
            append_jsonl(rejected_path, {
                "line": idx,
                "error": error_msg,
                "quality": quality,
                "raw": raw_obj
            })
            failed += 1
            continue
        
        # Validate sample content
        quality = validate_sample_obj(sample, symbols_map, config)
        
        # Track warnings regardless of pass/fail
        for warning in quality["warnings"]:
            warning_counter[warning["code"]] += 1
        if quality.get("checks", {}).get("trace") == "warn":
            trace_warning_samples += 1

        # Check if passed all validations
        if quality["passed"]:
            passed += 1
            if clean_path and write_clean:
                sample_dict = sample.model_dump()
                sample_dict["quality"] = quality
                append_jsonl(clean_path, sample_dict)
        else:
            failed += 1
            
            # Count errors
            for error in quality["errors"]:
                error_counter[error["code"]] += 1
            
            # Write to rejected
            append_jsonl(rejected_path, {
                "line": idx,
                "scenario": sample.scenario,
                "instruction": sample.instruction[:100] + "..." if len(sample.instruction) > 100 else sample.instruction,
                "quality": quality,
                "raw": raw_obj
            })
    
    # Calculate statistics
    pass_rate = passed / total if total > 0 else 0.0
    
    # Get top failures
    top_failures = [
        {"error": error, "count": count}
        for error, count in error_counter.most_common(20)
    ]
    
    top_warnings = [
        {"warning": warning, "count": count}
        for warning, count in warning_counter.most_common(10)
    ]
    
    trace_warning_counts = {
        code: count
        for code, count in warning_counter.items()
        if code.startswith("TRACE_")
    }

    # Generate report
    report = {
        "input_file": str(input_jsonl),
        "symbols_count": len(symbols_map),
        "gate_version": "v1",
        "validation_stats": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 4)
        },
        "top_failures": top_failures,
        "top_warnings": top_warnings,
        "trace_summary": {
            "warning_samples": trace_warning_samples,
            "warning_rate": round(trace_warning_samples / total, 4) if total else 0.0,
            "warning_counts": trace_warning_counts,
        },
        "output_files": {
            "rejected": str(rejected_path),
            "report": str(report_path),
            "clean": str(clean_path) if clean_path and write_clean else ""
        }
    }
    
    # Write report
    write_json(report_path, report)
    
    # Print summary
    print("=" * 70)
    print(" Dataset Validation Report")
    print("=" * 70)
    print(f"Input file: {input_jsonl}")
    print(f"Total samples: {total}")
    print(f"Passed: {passed} ({pass_rate:.2%})")
    print(f"Failed: {failed}")
    print()
    
    if top_failures:
        print("Top Failures:")
        for item in top_failures[:10]:
            print(f"  - {item['error']}: {item['count']}")
        print()
    
    if top_warnings:
        print("Top Warnings:")
        for item in top_warnings[:5]:
            print(f"  - {item['warning']}: {item['count']}")
        print()
    
    print(f"Rejected samples written to: {rejected_path}")
    print(f"Full report written to: {report_path}")
    print("=" * 70)


def validate_file(
    input_jsonl: Path | str,
    symbols_jsonl: Path | str,
    output_dir: Path | str = None
) -> dict[str, Any]:
    """
    Convenience function to validate a JSONL file.
    
    Args:
        input_jsonl: Path to input JSONL file
        symbols_jsonl: Path to symbols JSONL file
        output_dir: Output directory (default: same as input_jsonl)
        
    Returns:
        Validation report dict
    """
    input_jsonl = Path(input_jsonl)
    
    # Determine output directory
    if output_dir is None:
        output_dir = input_jsonl.parent
    else:
        output_dir = Path(output_dir)
    
    # Generate output paths
    base_name = input_jsonl.stem
    report_path = output_dir / f"{base_name}_validation_report.json"
    rejected_path = output_dir / f"{base_name}_rejected.jsonl"
    
    # Load symbols
    print(f"Loading symbols from {symbols_jsonl}...")
    symbols_map = load_symbols_map(symbols_jsonl)
    
    # Validate dataset
    print(f"Validating {input_jsonl}...")
    validate_dataset(input_jsonl, symbols_map, report_path, rejected_path)
    
    # Load and return report
    return read_jsonl(report_path)[0] if report_path.exists() else {}
