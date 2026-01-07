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
        qa_paths = []
        if not (self.args.skip_llm or self.args.skip_qa):
            artifacts = self.config.get("artifacts", {})
            qa_paths.append(
                Path(artifacts.get("auto_qa_raw_jsonl", "data/intermediate/auto_qa_raw.jsonl"))
            )
            qa_paths.append(self.paths.get("qa_raw_jsonl"))
            # De-duplicate paths while preserving order.
            seen = set()
            qa_paths = [p for p in qa_paths if p and not (p in seen or seen.add(p))]
            if qa_paths:
                self.logger.info(
                    "Using QA sources: %s",
                    ", ".join(p.name for p in qa_paths),
                )
        
        # Load QA samples
        if qa_paths:
            loaded_any = False
            for qa_path in qa_paths:
                if qa_path.exists():
                    qa_samples = read_jsonl(qa_path)
                    all_samples.extend(qa_samples)
                    self.logger.info(f"Loaded {len(qa_samples)} QA samples from {qa_path.name}")
                    loaded_any = True
                else:
                    self.logger.warning(f"QA samples not found: {qa_path}")
            if not loaded_any:
                self.logger.warning("No QA samples loaded from configured sources")
        
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
