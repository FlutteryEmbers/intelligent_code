"""
Step 6: Deduplication
"""
from src.utils.data.dedup import dedup_jsonl_by_simhash, dedup_jsonl_by_semantic
from src.utils.io.file_ops import read_json, write_json
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
        if self.args.skip_dedup:
            return True, "skip_flag"
        
        if not self.paths["all_raw_jsonl"].exists():
            return True, "no_samples"
        
        return False, ""
    
    def execute(self) -> dict:
        """Execute deduplication."""
        dedup_config = self.config.get("dedup", {})
        generation_config = self.config.get("generation", {})
        
        dedup_jsonl_by_simhash(
            input_jsonl=self.paths["all_raw_jsonl"],
            output_jsonl=self.paths["all_dedup_jsonl"],
            mapping_json=self.paths["dedup_mapping_json"],
            bits=dedup_config.get("simhash_bits", 64),
            seed=generation_config.get("seed", 42),
            max_hamming=dedup_config.get("max_hamming", 3)
        )

        semantic_cfg = dedup_config.get("semantic", {}) or {}
        if semantic_cfg.get("enabled", False):
            embedding_model = semantic_cfg.get("embedding_model")
            if not embedding_model:
                embedding_model = self.config.get("question_answer.embedding_model", "nomic-embed-text")
            semantic_mapping = dedup_jsonl_by_semantic(
                input_jsonl=self.paths["all_dedup_jsonl"],
                output_jsonl=self.paths["all_dedup_jsonl"],
                embedding_model=embedding_model,
                threshold=float(semantic_cfg.get("threshold", 0.92)),
                batch_size=int(semantic_cfg.get("batch_size", 64)),
                max_candidates=int(semantic_cfg.get("max_candidates", 2000)),
            )
            mapping_path = self.paths["dedup_mapping_json"]
            mapping = read_json(mapping_path) if mapping_path.exists() else {}
            mapping["semantic"] = semantic_mapping
            write_json(mapping_path, mapping)
        
        return {"status": "success"}
