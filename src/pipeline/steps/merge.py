"""
Step 5: Merge Samples
"""
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
        auto_config = self.config.get("auto", {})
        if auto_config.get("enabled", False):
            auto_outputs = auto_config.get("outputs", {})
            # Extract filename from path (in case outputs contains full path)
            qa_filename = auto_outputs.get("auto_qa_raw_jsonl", "auto_qa_raw.jsonl")
            if "/" in qa_filename or "\\" in qa_filename:
                # If full path provided, extract just the filename
                qa_filename = qa_filename.split("/")[-1].split("\\")[-1]
            qa_path = self.paths["intermediate"] / qa_filename
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
