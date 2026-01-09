"""
Step 4: Validation
"""
from pathlib import Path

from src.utils.data.validator import load_symbols_map, validate_dataset
from src.pipeline.base_step import BaseStep


class ValidationStep(BaseStep):
    """Validate generated datasets."""
    
    @property
    def name(self) -> str:
        return "validation"
    
    @property
    def display_name(self) -> str:
        return "Step 4: Validating Datasets"
    
    def execute(self) -> dict:
        """Execute validation."""
        symbols_map = load_symbols_map(self.paths["symbols_jsonl"])
        artifacts = self.config.get("artifacts", {})
        qa_clean_path = artifacts.get(
            "qa_clean_jsonl",
            str(self.paths.get("qa_clean_jsonl", self.paths["intermediate"] / "clean" / "qa_clean.jsonl")),
        )
        design_clean_path = artifacts.get(
            "design_clean_jsonl",
            str(self.paths.get("design_clean_jsonl", self.paths["intermediate"] / "clean" / "design_clean.jsonl")),
        )
        
        # Validate QA
        qa_paths = []
        qa_paths.append(
            artifacts.get("auto_qa_raw_jsonl", "data/intermediate/auto_qa_raw.jsonl")
        )
        qa_paths.append(self.paths.get("qa_raw_jsonl"))
        seen = set()
        qa_paths = [p for p in qa_paths if p and not (p in seen or seen.add(p))]
        for qa_path in qa_paths:
            qa_path = Path(qa_path)
            if qa_path.exists():
                self.logger.info("Validating QA samples from %s...", qa_path.name)
                validate_dataset(
                    qa_path,
                    symbols_map,
                    self.paths["qa_quality_json"],
                    self.paths["intermediate"] / "rejected" / "qa_validation_rejected.jsonl",
                    qa_clean_path,
                    self.config,
                )
                break
        
        # Validate Design
        if self.paths["design_raw_jsonl"].exists():
            self.logger.info("Validating design samples...")
            validate_dataset(
                self.paths["design_raw_jsonl"],
                symbols_map,
                self.paths["design_quality_json"],
                self.paths["intermediate"] / "rejected" / "design_validation_rejected.jsonl",
                design_clean_path,
                self.config,
            )
        
        return {"status": "success"}
