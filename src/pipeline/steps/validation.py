"""
Step 4: Validation
"""
from src.utils import load_symbols_map, validate_dataset
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
        
        # Validate QA
        if self.paths["qa_raw_jsonl"].exists():
            self.logger.info("Validating QA samples...")
            validate_dataset(
                self.paths["qa_raw_jsonl"],
                symbols_map,
                self.paths["qa_quality_json"],
                self.paths["intermediate"] / "qa_validation_rejected.jsonl"
            )
        
        # Validate Design
        if self.paths["design_raw_jsonl"].exists():
            self.logger.info("Validating design samples...")
            validate_dataset(
                self.paths["design_raw_jsonl"],
                symbols_map,
                self.paths["design_quality_json"],
                self.paths["intermediate"] / "design_validation_rejected.jsonl"
            )
        
        return {"status": "success"}
