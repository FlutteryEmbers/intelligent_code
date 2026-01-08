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


def validate_sample_obj(
    sample: TrainingSample, 
    symbols_map: dict[str, CodeSymbol]
) -> dict[str, Any]:
    """
    Validate a single TrainingSample against symbols map.
    
    Args:
        sample: TrainingSample to validate
        symbols_map: symbol_id -> CodeSymbol mapping
        
    Returns:
        Dict with:
        - schema_ok: bool - Sample passed schema validation
        - evidence_ok: bool - All evidence refs are valid
        - commit_ok: bool - Repo commits match
        - errors: list[str] - List of validation errors
        - warnings: list[str] - List of warnings
    """
    result = {
        "schema_ok": True,  # If we got here, schema is OK
        "evidence_ok": True,
        "commit_ok": True,
        "errors": [],
        "warnings": []
    }
    
    # Check if sample has thought and evidence_refs
    if not sample.thought or not sample.thought.evidence_refs:
        result["evidence_ok"] = False
        result["errors"].append("Missing thought.evidence_refs")
        return result
    
    # Validate each evidence ref
    for idx, ref in enumerate(sample.thought.evidence_refs):
        ref_id = f"evidence_refs[{idx}]"
        
        # Normalize symbol_id for cross-platform path comparison
        normalized_symbol_id = normalize_path_separators(ref.symbol_id)
        
        # Check if symbol_id exists
        if normalized_symbol_id not in symbols_map:
            result["evidence_ok"] = False
            result["errors"].append(f"{ref_id}: symbol_id '{ref.symbol_id}' not found in symbols map")
            continue
        
        symbol = symbols_map[normalized_symbol_id]
        
        # Check source_hash matches
        if ref.source_hash != symbol.source_hash:
            result["evidence_ok"] = False
            result["errors"].append(
                f"{ref_id}: source_hash mismatch (expected {symbol.source_hash[:8]}..., "
                f"got {ref.source_hash[:8]}...)"
            )
        
        # Check line range is valid
        if ref.start_line < 1 or ref.end_line < ref.start_line:
            result["evidence_ok"] = False
            result["errors"].append(
                f"{ref_id}: invalid line range [{ref.start_line}, {ref.end_line}]"
            )
        
        # Check if line range is within symbol bounds
        # Assume symbol has line info in symbol_id (format: file:class:line)
        # This is a soft check - just warn if suspicious
        if ref.end_line - ref.start_line > 500:
            result["warnings"].append(
                f"{ref_id}: suspiciously large line range ({ref.end_line - ref.start_line} lines)"
            )
        
        # Check file_path matches symbol
        normalized_ref_path = normalize_path_separators(ref.file_path)
        normalized_symbol_path = normalize_path_separators(symbol.file_path)
        if normalized_ref_path != normalized_symbol_path:
            result["evidence_ok"] = False
            result["errors"].append(
                f"{ref_id}: file_path mismatch (expected {symbol.file_path}, got {ref.file_path})"
            )
        
        # Check commit consistency (skip if UNKNOWN_COMMIT)
        if sample.repo_commit != "UNKNOWN_COMMIT" and symbol.repo_commit != "UNKNOWN_COMMIT":
            if sample.repo_commit != symbol.repo_commit:
                result["commit_ok"] = False
                result["errors"].append(
                    f"{ref_id}: repo_commit mismatch "
                    f"(sample: {sample.repo_commit[:8]}..., symbol: {symbol.repo_commit[:8]}...)"
                )
    
    return result


def validate_dataset(
    input_jsonl: Path | str,
    symbols_map: dict[str, CodeSymbol],
    report_path: Path | str,
    rejected_path: Path | str
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
    
    # Statistics
    total = 0
    passed = 0
    failed = 0
    error_counter = Counter()
    warning_counter = Counter()
    
    # Ensure rejected file is empty
    if rejected_path.exists():
        rejected_path.unlink()
    
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
            error_counter[error_msg] += 1
            
            # Write to rejected
            append_jsonl(rejected_path, {
                "line": idx,
                "error": error_msg,
                "quality": {
                    "schema_ok": False,
                    "evidence_ok": False,
                    "commit_ok": False,
                    "errors": [error_msg]
                },
                "raw": raw_obj
            })
            failed += 1
            continue
        
        # Validate sample content
        quality = validate_sample_obj(sample, symbols_map)
        
        # Check if passed all validations
        if quality["evidence_ok"] and quality["commit_ok"] and not quality["errors"]:
            passed += 1
        else:
            failed += 1
            
            # Count errors
            for error in quality["errors"]:
                # Extract error type (first part before ':')
                error_type = error.split(":")[0] if ":" in error else error
                error_counter[error_type] += 1
            
            # Count warnings
            for warning in quality["warnings"]:
                warning_type = warning.split(":")[0] if ":" in warning else warning
                warning_counter[warning_type] += 1
            
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
    
    # Generate report
    report = {
        "input_file": str(input_jsonl),
        "symbols_count": len(symbols_map),
        "validation_stats": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 4)
        },
        "top_failures": top_failures,
        "top_warnings": top_warnings,
        "output_files": {
            "rejected": str(rejected_path),
            "report": str(report_path)
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
