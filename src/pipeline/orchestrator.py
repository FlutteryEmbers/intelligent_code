"""
Pipeline orchestrator for intelligent training data generation.
"""
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils import get_logger, write_json
from src.utils.config import Config
from src.pipeline.helpers import get_repo_commit
from src.pipeline.steps import (
    ParseStep,
    AutoModuleStep,
    QAGenerationStep,
    DesignGenerationStep,
    ValidationStep,
    MergeStep,
    DeduplicationStep,
    SecretsScanStep,
    SplitStep,
    ExportStep,
)

logger = get_logger(__name__)


class Pipeline:
    """Main pipeline orchestrator."""
    
    def __init__(self, config_path: str):
        """
        Initialize pipeline.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        
        # Load configuration
        logger.info("=" * 70)
        logger.info(" Intelligent Training Data Generation Pipeline")
        logger.info("=" * 70)
        logger.info(f"Loading configuration from {config_path}")
        
        self.config_instance = Config()
        self.config_instance.reload(config_path)
        self.config = self.config_instance.get_config()
        
        # Initialize paths
        self.paths = self._init_paths()
        
        # Initialize summary
        self.summary = {
            "start_time": datetime.now().isoformat(),
            "config_file": str(config_path),
            "steps": {}
        }
    
    def _init_paths(self) -> dict:
        """Initialize and create all directory paths."""
        cfg = self.config
        
        # Base directories
        raw_extracted = Path(cfg["output"]["raw_extracted"])
        raw_repo_meta = Path(cfg["output"]["raw_repo_meta"])
        intermediate = Path(cfg["output"]["intermediate"])
        final = Path(cfg["output"]["final"])
        reports = Path(cfg["output"]["reports"])
        
        # Separate QA and Design directories
        qa_final = Path(cfg["paths"].get("qa_final_dir", "data/final/qa"))
        design_final = Path(cfg["paths"].get("design_final_dir", "data/final/design"))
        
        # Create all directories
        for directory in [raw_extracted, raw_repo_meta, intermediate, final, reports, qa_final, design_final]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Define all file paths
        paths = {
            # Directories
            "raw_extracted": raw_extracted,
            "raw_repo_meta": raw_repo_meta,
            "intermediate": intermediate,
            "final": final,
            "reports": reports,
            "qa_final": qa_final,
            "design_final": design_final,
            
            # Raw outputs
            "symbols_jsonl": raw_extracted / "symbols.jsonl",
            "repo_meta_json": raw_repo_meta / "repo_meta.json",
            
            # Intermediate outputs
            "qa_raw_jsonl": intermediate / "qa_raw.jsonl",
            "qa_rejected_jsonl": intermediate / "qa_rejected.jsonl",
            "design_raw_jsonl": intermediate / "design_raw.jsonl",
            "design_rejected_jsonl": intermediate / "design_rejected.jsonl",
            "all_raw_jsonl": intermediate / "all_raw.jsonl",
            "all_dedup_jsonl": intermediate / "all_dedup.jsonl",
            
            # Reports
            "dedup_mapping_json": reports / "dedup_mapping.json",
            "qa_quality_json": reports / "qa_quality.json",
            "design_quality_json": reports / "design_quality.json",
            "secrets_dropped_jsonl": reports / "secrets_dropped.jsonl",
            "pipeline_summary_json": reports / "pipeline_summary.json",
            
            # Final outputs (combined)
            "train_jsonl": final / "train.jsonl",
            "val_jsonl": final / "val.jsonl",
            "test_jsonl": final / "test.jsonl",
            "train_sft_jsonl": final / "train_sft.jsonl",
            "val_sft_jsonl": final / "val_sft.jsonl",
            "test_sft_jsonl": final / "test_sft.jsonl",
            
            # QA outputs
            "qa_train_jsonl": qa_final / "train.jsonl",
            "qa_val_jsonl": qa_final / "val.jsonl",
            "qa_test_jsonl": qa_final / "test.jsonl",
            "qa_train_sft_jsonl": qa_final / "train_sft.jsonl",
            "qa_val_sft_jsonl": qa_final / "val_sft.jsonl",
            "qa_test_sft_jsonl": qa_final / "test_sft.jsonl",
            
            # Design outputs
            "design_train_jsonl": design_final / "train.jsonl",
            "design_val_jsonl": design_final / "val.jsonl",
            "design_test_jsonl": design_final / "test.jsonl",
            "design_train_sft_jsonl": design_final / "train_sft.jsonl",
            "design_val_sft_jsonl": design_final / "val_sft.jsonl",
            "design_test_sft_jsonl": design_final / "test_sft.jsonl",
        }
        
        return paths
    
    def run(self, args: Any):
        """
        Run the complete pipeline.
        
        Args:
            args: Command line arguments
        """
        # Get repository commit
        repo_path = Path(self.config["repo"]["path"])
        config_commit = self.config["repo"].get("commit", "")
        repo_commit = get_repo_commit(repo_path, config_commit)
        
        logger.info(f"Repository commit: {repo_commit}")
        logger.info(f"Repository path: {repo_path}")
        
        # Store in summary
        self.summary["repo_path"] = str(repo_path)
        self.summary["repo_commit"] = repo_commit
        
        # Define pipeline steps
        steps = [
            ParseStep(self.config, args, self.paths, repo_commit),
            AutoModuleStep(self.config, args, self.paths, repo_commit),
            QAGenerationStep(self.config, args, self.paths, repo_commit),
            DesignGenerationStep(self.config, args, self.paths, repo_commit),
            ValidationStep(self.config, args, self.paths, repo_commit),
            MergeStep(self.config, args, self.paths, repo_commit),
            DeduplicationStep(self.config, args, self.paths, repo_commit),
            SecretsScanStep(self.config, args, self.paths, repo_commit),
            SplitStep(self.config, args, self.paths, repo_commit),
            ExportStep(self.config, args, self.paths, repo_commit),
        ]
        
        # Execute each step
        for step in steps:
            result = step.run()
            self.summary["steps"][step.name] = result
        
        # Write final summary
        self.write_summary()
    
    def write_summary(self):
        """Write pipeline summary to file."""
        self.summary["end_time"] = datetime.now().isoformat()
        self.summary["output_files"] = {
            "symbols": str(self.paths["symbols_jsonl"]),
            "repo_meta": str(self.paths["repo_meta_json"]),
            "train_sft": str(self.paths["train_sft_jsonl"]),
            "val_sft": str(self.paths["val_sft_jsonl"]),
            "test_sft": str(self.paths["test_sft_jsonl"]),
            "reports": str(self.paths["reports"])
        }
        
        write_json(self.paths["pipeline_summary_json"], self.summary)
        
        logger.info("=" * 70)
        logger.info(" Pipeline Completed")
        logger.info("=" * 70)
        logger.info(f"Summary written to: {self.paths['pipeline_summary_json']}")
        logger.info(f"Training data: {self.paths['train_sft_jsonl']}")
        logger.info(f"Validation data: {self.paths['val_sft_jsonl']}")
        logger.info(f"Test data: {self.paths['test_sft_jsonl']}")
        logger.info("=" * 70)
