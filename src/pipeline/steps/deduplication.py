"""
Step 6: Deduplication
"""
from src.utils import dedup_jsonl_by_simhash
from src.pipeline.base_step import BaseStep


class DeduplicationStep(BaseStep):
    """Deduplicate samples using simhash."""
    
    @property
    def name(self) -> str:
        return "deduplication"
    
    @property
    def display_name(self) -> str:
        return "Step 6: Deduplicating Samples"
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if deduplication should be skipped."""
        if not self.config.get("quality", {}).get("enable_deduplication", True):
            return True, "disabled"
        
        if not self.paths["all_raw_jsonl"].exists():
            return True, "no_samples"
        
        return False, ""
    
    def execute(self) -> dict:
        """Execute deduplication."""
        dedup_config = self.config.get("dedup", {})
        
        dedup_jsonl_by_simhash(
            input_jsonl=self.paths["all_raw_jsonl"],
            output_jsonl=self.paths["all_dedup_jsonl"],
            mapping_json=self.paths["dedup_mapping_json"],
            max_hamming=dedup_config.get("max_hamming", 3)
        )
        
        return {"status": "success"}
