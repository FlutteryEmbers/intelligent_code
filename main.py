"""
Main pipeline for intelligent training data generation.
Orchestrates parsing, generation, validation, deduplication, splitting, and export.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils import (
    get_logger,
    read_json,
    write_json,
    read_jsonl,
    write_jsonl,
    load_symbols_map,
    validate_dataset,
    dedup_jsonl_by_simhash,
    group_split_samples,
    export_sft_jsonl,
    export_statistics,
    detect_license,
    scan_secrets,
    sanitize_text,
)
from src.utils.config import Config
from src.parser.java_parser import JavaParser
from src.engine.qa_generator import QAGenerator
from src.engine.design_generator import DesignGenerator
from src.engine.demo_method_understander import DemoMethodUnderstander
from src.engine.demo_question_generator import DemoQuestionGenerator
from src.engine.demo_answer_generator import DemoAnswerGenerator
from src.utils import vector_index


logger = get_logger(__name__)


def get_repo_commit(repo_path: Path, config_commit: str = None) -> str:
    """
    Get repository commit hash.
    
    Priority:
    1. config_commit if provided and non-empty
    2. git rev-parse HEAD if repo_path is a git repository
    3. "UNKNOWN_COMMIT" as fallback
    
    Args:
        repo_path: Path to repository
        config_commit: Commit hash from config (if any)
        
    Returns:
        Commit hash string
    """
    # Use config commit if provided
    if config_commit and config_commit.strip():
        logger.info(f"Using commit from config: {config_commit}")
        return config_commit.strip()
    
    # Try to get commit from git
    repo_path = Path(repo_path)
    git_dir = repo_path / ".git"
    
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                logger.info(f"Got commit from git: {commit[:8]}...")
                return commit
        except Exception as e:
            logger.warning(f"Failed to get git commit: {e}")
    
    # Fallback
    logger.warning("Using UNKNOWN_COMMIT as fallback")
    return "UNKNOWN_COMMIT"


def should_skip_parse(repo_meta_path: Path, symbols_path: Path, current_commit: str) -> bool:
    """
    Check if parsing can be skipped based on cache.
    
    Args:
        repo_meta_path: Path to repo_meta.json
        symbols_path: Path to symbols.jsonl
        current_commit: Current repository commit
        
    Returns:
        True if parsing can be skipped, False otherwise
    """
    # Check if files exist
    if not repo_meta_path.exists() or not symbols_path.exists():
        return False
    
    # Check if commit matches
    repo_meta = read_json(repo_meta_path)
    if not repo_meta:
        return False
    
    cached_commit = repo_meta.get("repo_commit", "")
    if cached_commit != current_commit:
        logger.info(f"Commit mismatch: cached={cached_commit[:8]}, current={current_commit[:8]}")
        return False
    
    logger.info(f"Cache hit: using existing symbols (commit={current_commit[:8]})")
    return True


def merge_samples(qa_path: Path, design_path: Path, output_path: Path) -> int:
    """
    Merge QA and design samples into single file.
    
    Args:
        qa_path: Path to QA samples
        design_path: Path to design samples
        output_path: Output path for merged samples
        
    Returns:
        Total number of samples merged
    """
    all_samples = []
    
    # Load QA samples
    if qa_path.exists():
        qa_samples = read_jsonl(qa_path)
        all_samples.extend(qa_samples)
        logger.info(f"Loaded {len(qa_samples)} QA samples")
    else:
        logger.warning(f"QA samples not found: {qa_path}")
    
    # Load design samples
    if design_path.exists():
        design_samples = read_jsonl(design_path)
        all_samples.extend(design_samples)
        logger.info(f"Loaded {len(design_samples)} design samples")
    else:
        logger.warning(f"Design samples not found: {design_path}")
    
    # Write merged samples
    if all_samples:
        write_jsonl(output_path, all_samples)
        logger.info(f"Merged {len(all_samples)} samples to {output_path}")
    
    return len(all_samples)


def scan_and_filter_secrets(
    samples: list[dict],
    mode: str = "drop",
    report_path: Path = None
) -> list[dict]:
    """
    Scan samples for secrets and filter based on mode.
    
    Args:
        samples: List of samples to scan
        mode: "drop" (remove samples with secrets) or "sanitize" (redact secrets)
        report_path: Path to write dropped samples report
        
    Returns:
        Filtered samples
    """
    clean_samples = []
    dropped_samples = []
    
    for idx, sample in enumerate(samples):
        # Scan context and answer
        context = sample.get("context", "")
        answer = sample.get("answer", "")
        scan_text = context + "\n" + answer
        
        findings = scan_secrets(scan_text)
        
        if findings:
            logger.warning(f"Sample {idx}: found {len(findings)} potential secrets")
            
            if mode == "drop":
                # Drop this sample
                dropped_samples.append({
                    "index": idx,
                    "scenario": sample.get("scenario"),
                    "instruction": sample.get("instruction", "")[:100],
                    "findings": findings
                })
            elif mode == "sanitize":
                # Sanitize and keep
                sample["context"] = sanitize_text(context, findings)
                sample["answer"] = sanitize_text(answer, findings)
                clean_samples.append(sample)
        else:
            clean_samples.append(sample)
    
    # Write report
    if dropped_samples and report_path:
        write_jsonl(report_path, dropped_samples)
        logger.info(f"Dropped {len(dropped_samples)} samples with secrets (see {report_path})")
    
    return clean_samples


def main():
    """Main pipeline execution."""
    parser = argparse.ArgumentParser(
        description="Intelligent training data generation pipeline"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/pipeline.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--skip-parse",
        action="store_true",
        help="Skip parsing step (use existing symbols.jsonl)"
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip all LLM generation (QA + design)"
    )
    parser.add_argument(
        "--skip-qa",
        action="store_true",
        help="Skip QA generation"
    )
    parser.add_argument(
        "--skip-design",
        action="store_true",
        help="Skip design generation"
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip final export step"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    logger.info("=" * 70)
    logger.info(" Intelligent Training Data Generation Pipeline")
    logger.info("=" * 70)
    logger.info(f"Loading configuration from {args.config}")
    
    from src.utils.config import Config
    config_instance = Config()
    config_instance.reload(args.config)
    cfg = config_instance.get_config()
    
    # Extract paths
    repo_path = Path(cfg["repo"]["path"])
    config_commit = cfg["repo"].get("commit", "")
    
    # Output directories
    raw_extracted = Path(cfg["output"]["raw_extracted"])
    raw_repo_meta = Path(cfg["output"]["raw_repo_meta"])
    intermediate = Path(cfg["output"]["intermediate"])
    final = Path(cfg["output"]["final"])
    reports = Path(cfg["output"]["reports"])
    
    # Create directories
    for directory in [raw_extracted, raw_repo_meta, intermediate, final, reports]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Get repo commit
    repo_commit = get_repo_commit(repo_path, config_commit)
    logger.info(f"Repository commit: {repo_commit}")
    
    # Define file paths
    symbols_jsonl = raw_extracted / "symbols.jsonl"
    repo_meta_json = raw_repo_meta / "repo_meta.json"
    qa_raw_jsonl = intermediate / "qa_raw.jsonl"
    qa_rejected_jsonl = intermediate / "qa_rejected.jsonl"
    design_raw_jsonl = intermediate / "design_raw.jsonl"
    design_rejected_jsonl = intermediate / "design_rejected.jsonl"
    all_raw_jsonl = intermediate / "all_raw.jsonl"
    all_dedup_jsonl = intermediate / "all_dedup.jsonl"
    dedup_mapping_json = reports / "dedup_mapping.json"
    qa_quality_json = reports / "qa_quality.json"
    design_quality_json = reports / "design_quality.json"
    secrets_dropped_jsonl = reports / "secrets_dropped.jsonl"
    train_jsonl = final / "train.jsonl"
    val_jsonl = final / "val.jsonl"
    test_jsonl = final / "test.jsonl"
    train_sft_jsonl = final / "train_sft.jsonl"
    val_sft_jsonl = final / "val_sft.jsonl"
    test_sft_jsonl = final / "test_sft.jsonl"
    pipeline_summary_json = reports / "pipeline_summary.json"
    
    summary = {
        "start_time": datetime.now().isoformat(),
        "config_file": str(args.config),
        "repo_path": str(repo_path),
        "repo_commit": repo_commit,
        "steps": {}
    }
    
    # ========== Step 1: Parse Repository ==========
    if args.skip_parse and should_skip_parse(repo_meta_json, symbols_jsonl, repo_commit):
        logger.info("Skipping parse (using cache)")
        summary["steps"]["parse"] = {"status": "skipped", "reason": "cache_hit"}
    else:
        logger.info("=" * 70)
        logger.info(" Step 1: Parsing Repository")
        logger.info("=" * 70)
        
        try:
            java_parser = JavaParser(cfg)
            symbols = java_parser.parse_repo(repo_path, repo_commit)
            
            # Add license info
            license_info = detect_license(repo_path)
            
            # Build repo_meta
            repo_meta = {
                "repo_path": str(repo_path),
                "repo_commit": repo_commit,
                "total_symbols": len(symbols),
                "license": license_info
            }
            
            # Write outputs
            write_jsonl(symbols_jsonl, [s.model_dump() for s in symbols])
            write_json(repo_meta_json, repo_meta)
            
            logger.info(f"Parsed {len(symbols)} symbols")
            logger.info(f"License: {license_info.get('name', 'Unknown')}")
            
            summary["steps"]["parse"] = {
                "status": "success",
                "symbols_count": len(symbols),
                "license": license_info.get("name")
            }
        except Exception as e:
            logger.error(f"Parse failed: {e}", exc_info=True)
            summary["steps"]["parse"] = {"status": "failed", "error": str(e)}
            # Don't exit - continue with existing symbols if available
    
    # ========== Demo Module: Method-Level RAG Pipeline ==========
    if cfg.demo.enabled:
        logger.info("=" * 70)
        logger.info(" Demo Module: Method-Level Understanding & Question Generation")
        logger.info("=" * 70)
        
        try:
            # Prepare paths
            method_profiles_jsonl = cfg.demo.method_profiles
            method_embeddings_jsonl = cfg.demo.method_embeddings
            questions_jsonl = cfg.demo.questions
            demo_qa_jsonl = cfg.demo.demo_qa_raw
            
            # Load symbols for demo processing
            symbols_map = load_symbols_map(symbols_jsonl)
            if not symbols_map:
                logger.warning("No symbols found for demo module, skipping")
                summary["steps"]["demo"] = {"status": "skipped", "reason": "no_symbols"}
            else:
                # Step D1: Method Understanding
                logger.info(f"Step D1: Analyzing methods (max: {cfg.demo.max_methods})")
                understander = DemoMethodUnderstander(cfg)
                method_profiles = understander.generate_from_symbols(
                    symbols_map=symbols_map,
                    repo_commit=repo_commit
                )
                logger.info(f"Generated {len(method_profiles)} method profiles")
                
                # Step D2: Build Vector Embeddings
                logger.info(f"Step D2: Building embeddings (model: {cfg.demo.embedding_model})")
                vector_index.build_embeddings(
                    profiles_jsonl=method_profiles_jsonl,
                    embeddings_jsonl=method_embeddings_jsonl,
                    embedding_model=cfg.demo.embedding_model
                )
                logger.info(f"Embeddings saved to {method_embeddings_jsonl.name}")
                
                # Step D3: Generate Questions
                logger.info(f"Step D3: Generating questions ({cfg.demo.questions_per_method} per method)")
                question_gen = DemoQuestionGenerator(cfg)
                questions = question_gen.generate_from_profiles(
                    profiles_jsonl=method_profiles_jsonl,
                    repo_commit=repo_commit
                )
                logger.info(f"Generated {len(questions)} questions")
                
                # Step D4: Generate Answers with Vector Retrieval
                logger.info(f"Step D4: Generating answers (top_k: {cfg.demo.top_k_context})")
                answer_gen = DemoAnswerGenerator(cfg)
                qa_samples = answer_gen.generate_from_questions(
                    questions_jsonl=questions_jsonl,
                    embeddings_jsonl=method_embeddings_jsonl,
                    profiles_jsonl=method_profiles_jsonl,
                    symbols_map=symbols_map,
                    repo_commit=repo_commit
                )
                logger.info(f"Generated {len(qa_samples)} demo QA samples")
                
                summary["steps"]["demo"] = {
                    "status": "success",
                    "method_profiles": len(method_profiles),
                    "questions": len(questions),
                    "qa_samples": len(qa_samples)
                }
                
        except Exception as e:
            logger.error(f"Demo module failed: {e}", exc_info=True)
            summary["steps"]["demo"] = {"status": "failed", "error": str(e)}
            # Continue pipeline even if demo fails
    else:
        logger.info("Demo module disabled (demo.enabled=false)")
        summary["steps"]["demo"] = {"status": "disabled"}
    
    # ========== Step 2: Generate QA Samples ==========
    if args.skip_llm or args.skip_qa:
        logger.info("Skipping QA generation")
        summary["steps"]["qa_generation"] = {"status": "skipped"}
    else:
        logger.info("=" * 70)
        logger.info(" Step 2: Generating QA Samples")
        logger.info("=" * 70)
        
        try:
            qa_gen = QAGenerator(cfg)
            qa_samples = qa_gen.generate_from_repo(
                symbols_path=symbols_jsonl,
                repo_commit=repo_commit
            )
            
            logger.info(f"Generated {len(qa_samples)} QA samples")
            summary["steps"]["qa_generation"] = {
                "status": "success",
                "samples_count": len(qa_samples)
            }
        except Exception as e:
            logger.error(f"QA generation failed: {e}", exc_info=True)
            summary["steps"]["qa_generation"] = {"status": "failed", "error": str(e)}
    
    # ========== Step 3: Generate Design Samples ==========
    if args.skip_llm or args.skip_design:
        logger.info("Skipping design generation")
        summary["steps"]["design_generation"] = {"status": "skipped"}
    else:
        logger.info("=" * 70)
        logger.info(" Step 3: Generating Design Samples")
        logger.info("=" * 70)
        
        try:
            design_gen = DesignGenerator(cfg)
            design_samples = design_gen.generate_from_repo(
                symbols_path=symbols_jsonl,
                repo_commit=repo_commit
            )
            
            logger.info(f"Generated {len(design_samples)} design samples")
            summary["steps"]["design_generation"] = {
                "status": "success",
                "samples_count": len(design_samples)
            }
        except Exception as e:
            logger.error(f"Design generation failed: {e}", exc_info=True)
            summary["steps"]["design_generation"] = {"status": "failed", "error": str(e)}
    
    # ========== Step 4: Validate Datasets ==========
    logger.info("=" * 70)
    logger.info(" Step 4: Validating Datasets")
    logger.info("=" * 70)
    
    try:
        symbols_map = load_symbols_map(symbols_jsonl)
        
        # Validate QA
        if qa_raw_jsonl.exists():
            logger.info("Validating QA samples...")
            validate_dataset(
                qa_raw_jsonl,
                symbols_map,
                qa_quality_json,
                qa_rejected_jsonl.parent / "qa_validation_rejected.jsonl"
            )
        
        # Validate Design
        if design_raw_jsonl.exists():
            logger.info("Validating design samples...")
            validate_dataset(
                design_raw_jsonl,
                symbols_map,
                design_quality_json,
                design_rejected_jsonl.parent / "design_validation_rejected.jsonl"
            )
        
        summary["steps"]["validation"] = {"status": "success"}
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        summary["steps"]["validation"] = {"status": "failed", "error": str(e)}
    
    # ========== Step 5: Merge Samples ==========
    logger.info("=" * 70)
    logger.info(" Step 5: Merging Samples")
    logger.info("=" * 70)
    
    try:
        total_samples = merge_samples(qa_raw_jsonl, design_raw_jsonl, all_raw_jsonl)
        summary["steps"]["merge"] = {
            "status": "success",
            "total_samples": total_samples
        }
    except Exception as e:
        logger.error(f"Merge failed: {e}", exc_info=True)
        summary["steps"]["merge"] = {"status": "failed", "error": str(e)}
        total_samples = 0
    
    # ========== Step 6: Deduplication ==========
    if total_samples > 0 and cfg.get("quality", {}).get("enable_deduplication", True):
        logger.info("=" * 70)
        logger.info(" Step 6: Deduplicating Samples")
        logger.info("=" * 70)
        
        try:
            dedup_jsonl_by_simhash(
                input_jsonl=all_raw_jsonl,
                output_jsonl=all_dedup_jsonl,
                mapping_json=dedup_mapping_json,
                max_hamming=3
            )
            summary["steps"]["deduplication"] = {"status": "success"}
        except Exception as e:
            logger.error(f"Deduplication failed: {e}", exc_info=True)
            summary["steps"]["deduplication"] = {"status": "failed", "error": str(e)}
            # Use raw samples as fallback
            all_dedup_jsonl = all_raw_jsonl
    else:
        logger.info("Skipping deduplication")
        all_dedup_jsonl = all_raw_jsonl
        summary["steps"]["deduplication"] = {"status": "skipped"}
    
    # ========== Step 7: Secrets Scanning ==========
    logger.info("=" * 70)
    logger.info(" Step 7: Scanning for Secrets")
    logger.info("=" * 70)
    
    try:
        samples = read_jsonl(all_dedup_jsonl)
        safety_mode = cfg.get("safety", {}).get("mode", "drop")
        
        filtered_samples = scan_and_filter_secrets(
            samples=samples,
            mode=safety_mode,
            report_path=secrets_dropped_jsonl
        )
        
        # Overwrite dedup file with filtered samples
        if len(filtered_samples) < len(samples):
            write_jsonl(all_dedup_jsonl, filtered_samples)
            logger.info(f"Filtered to {len(filtered_samples)} samples (removed {len(samples) - len(filtered_samples)})")
        
        summary["steps"]["secrets_scan"] = {
            "status": "success",
            "mode": safety_mode,
            "filtered_count": len(samples) - len(filtered_samples)
        }
    except Exception as e:
        logger.error(f"Secrets scan failed: {e}", exc_info=True)
        summary["steps"]["secrets_scan"] = {"status": "failed", "error": str(e)}
    
    # ========== Step 8: Split Dataset ==========
    logger.info("=" * 70)
    logger.info(" Step 8: Splitting Dataset")
    logger.info("=" * 70)
    
    try:
        samples = read_jsonl(all_dedup_jsonl)
        symbols_map = load_symbols_map(symbols_jsonl)
        
        if len(samples) < 3:
            logger.warning(f"Too few samples ({len(samples)}) for splitting, using all for training")
            train_samples = samples
            val_samples = []
            test_samples = []
        else:
            train_samples, val_samples, test_samples = group_split_samples(
                samples=samples,
                symbols_map=symbols_map,
                train_ratio=0.8,
                val_ratio=0.1,
                test_ratio=0.1,
                seed=42,
                group_by="package"
            )
        
        # Write splits
        write_jsonl(train_jsonl, train_samples)
        write_jsonl(val_jsonl, val_samples)
        write_jsonl(test_jsonl, test_samples)
        
        summary["steps"]["split"] = {
            "status": "success",
            "train_count": len(train_samples),
            "val_count": len(val_samples),
            "test_count": len(test_samples)
        }
    except Exception as e:
        logger.error(f"Split failed: {e}", exc_info=True)
        summary["steps"]["split"] = {"status": "failed", "error": str(e)}
    
    # ========== Step 9: Export to SFT Format ==========
    if args.skip_export:
        logger.info("Skipping export")
        summary["steps"]["export"] = {"status": "skipped"}
    else:
        logger.info("=" * 70)
        logger.info(" Step 9: Exporting to SFT Format")
        logger.info("=" * 70)
        
        try:
            # Export each split
            if train_jsonl.exists():
                train_samples = read_jsonl(train_jsonl)
                export_sft_jsonl(train_samples, train_sft_jsonl)
            
            if val_jsonl.exists():
                val_samples = read_jsonl(val_jsonl)
                export_sft_jsonl(val_samples, val_sft_jsonl)
            
            if test_jsonl.exists():
                test_samples = read_jsonl(test_jsonl)
                export_sft_jsonl(test_samples, test_sft_jsonl)
            
            # Export statistics
            all_samples = train_samples + val_samples + test_samples
            stats = export_statistics(all_samples, reports / "dataset_stats.json")
            
            summary["steps"]["export"] = {
                "status": "success",
                "files": [
                    str(train_sft_jsonl),
                    str(val_sft_jsonl),
                    str(test_sft_jsonl)
                ]
            }
        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            summary["steps"]["export"] = {"status": "failed", "error": str(e)}
    
    # ========== Write Pipeline Summary ==========
    summary["end_time"] = datetime.now().isoformat()
    summary["output_files"] = {
        "symbols": str(symbols_jsonl),
        "repo_meta": str(repo_meta_json),
        "train_sft": str(train_sft_jsonl),
        "val_sft": str(val_sft_jsonl),
        "test_sft": str(test_sft_jsonl),
        "reports": str(reports)
    }
    
    write_json(pipeline_summary_json, summary)
    
    logger.info("=" * 70)
    logger.info(" Pipeline Completed")
    logger.info("=" * 70)
    logger.info(f"Summary written to: {pipeline_summary_json}")
    logger.info(f"Training data: {train_sft_jsonl}")
    logger.info(f"Validation data: {val_sft_jsonl}")
    logger.info(f"Test data: {test_sft_jsonl}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
