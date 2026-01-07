"""
Step 5: Merge Samples
"""
from pathlib import Path

from src.utils import read_jsonl, write_jsonl
from src.pipeline.base_step import BaseStep


class MergeStep(BaseStep):
    """Merge QA and design samples into single file."""
    
    @property
    def name(self) -> str:
        return "merge"
    
    @property
    def display_name(self) -> str:
        return "Step 5: Merging Samples"
    
    def execute(self) -> dict:
        """Execute merge."""
        all_samples = []
        
        # Determine which QA source to use
        if not self.args.skip_auto and not (self.args.skip_llm or self.args.skip_qa):
            artifacts = self.config.get("artifacts", {})
            qa_path = Path(artifacts.get("auto_qa_raw_jsonl", "data/intermediate/auto_qa_raw.jsonl"))
            self.logger.info(f"Using auto QA from {qa_path.name}")
        else:
            qa_path = self.paths["qa_raw_jsonl"]
        
        # Load QA samples
        if qa_path.exists():
            qa_samples = read_jsonl(qa_path)
            all_samples.extend(qa_samples)
            self.logger.info(f"Loaded {len(qa_samples)} QA samples")
        else:
            self.logger.warning(f"QA samples not found: {qa_path}")
        
        # Load design samples
        if self.paths["design_raw_jsonl"].exists():
            design_samples = read_jsonl(self.paths["design_raw_jsonl"])
            all_samples.extend(design_samples)
            self.logger.info(f"Loaded {len(design_samples)} design samples")
        else:
            self.logger.warning(f"Design samples not found: {self.paths['design_raw_jsonl']}")
        
        # Write merged samples
        if all_samples:
            write_jsonl(self.paths["all_raw_jsonl"], all_samples)
            self.logger.info(f"Merged {len(all_samples)} samples to {self.paths['all_raw_jsonl']}")
        
        return {
            "status": "success",
            "total_samples": len(all_samples)
        }
