"""
Step 8: Split Dataset
"""
from src.utils.io.file_ops import read_jsonl, write_jsonl
from src.utils.data.validator import load_symbols_map
from src.utils.data.splitter import group_split_samples
from src.pipeline.base_step import BaseStep


class SplitStep(BaseStep):
    """Split dataset into train/val/test sets."""
    
    @property
    def name(self) -> str:
        return "split"
    
    @property
    def display_name(self) -> str:
        return "Step 8: Splitting Dataset"
    
    def execute(self) -> dict:
        """Execute dataset splitting."""
        samples = read_jsonl(self.paths["all_dedup_jsonl"])
        symbols_map = load_symbols_map(self.paths["symbols_jsonl"])
        
        # Separate QA and Design samples
        qa_samples = [s for s in samples if s.get('scenario') == 'qa_rule']
        design_samples = [s for s in samples if s.get('scenario') == 'arch_design']
        
        self.logger.info(f"Total samples: {len(samples)} (QA: {len(qa_samples)}, Design: {len(design_samples)})")
        
        split_config = self.config.get("split", {})
        global_seed = self.config.get("generation", {}).get("seed", 42)
        
        # Split combined dataset (for backward compatibility)
        if len(samples) < 3:
            self.logger.warning(f"Too few samples ({len(samples)}) for splitting, using all for training")
            train_samples = samples
            val_samples = []
            test_samples = []
        else:
            train_samples, val_samples, test_samples = group_split_samples(
                samples=samples,
                symbols_map=symbols_map,
                train_ratio=split_config.get("train_ratio", 0.8),
                val_ratio=split_config.get("val_ratio", 0.1),
                test_ratio=split_config.get("test_ratio", 0.1),
                seed=global_seed,
                group_by=split_config.get("group_by", "package")
            )
        
        # Write combined splits
        write_jsonl(self.paths["train_jsonl"], train_samples)
        write_jsonl(self.paths["val_jsonl"], val_samples)
        write_jsonl(self.paths["test_jsonl"], test_samples)
        
        # Split QA samples separately
        if len(qa_samples) >= 3:
            qa_train, qa_val, qa_test = group_split_samples(
                samples=qa_samples,
                symbols_map=symbols_map,
                train_ratio=split_config.get("train_ratio", 0.8),
                val_ratio=split_config.get("val_ratio", 0.1),
                test_ratio=split_config.get("test_ratio", 0.1),
                seed=global_seed,
                group_by=split_config.get("group_by", "package")
            )
        elif len(qa_samples) > 0:
            qa_train = qa_samples
            qa_val = []
            qa_test = []
        else:
            qa_train = []
            qa_val = []
            qa_test = []
        
        # Write QA splits
        write_jsonl(self.paths["qa_train_jsonl"], qa_train)
        write_jsonl(self.paths["qa_val_jsonl"], qa_val)
        write_jsonl(self.paths["qa_test_jsonl"], qa_test)
        
        # Split Design samples separately
        if len(design_samples) >= 3:
            design_train, design_val, design_test = group_split_samples(
                samples=design_samples,
                symbols_map=symbols_map,
                train_ratio=split_config.get("train_ratio", 0.8),
                val_ratio=split_config.get("val_ratio", 0.1),
                test_ratio=split_config.get("test_ratio", 0.1),
                seed=global_seed,
                group_by=split_config.get("group_by", "package")
            )
        elif len(design_samples) > 0:
            design_train = design_samples
            design_val = []
            design_test = []
        else:
            design_train = []
            design_val = []
            design_test = []
        
        # Write Design splits
        write_jsonl(self.paths["design_train_jsonl"], design_train)
        write_jsonl(self.paths["design_val_jsonl"], design_val)
        write_jsonl(self.paths["design_test_jsonl"], design_test)

        qa_train_combined = [s for s in train_samples if s.get("scenario") == "qa_rule"]
        qa_val_combined = [s for s in val_samples if s.get("scenario") == "qa_rule"]
        qa_test_combined = [s for s in test_samples if s.get("scenario") == "qa_rule"]
        design_train_combined = [s for s in train_samples if s.get("scenario") == "arch_design"]
        design_val_combined = [s for s in val_samples if s.get("scenario") == "arch_design"]
        design_test_combined = [s for s in test_samples if s.get("scenario") == "arch_design"]
        
        return {
            "status": "success",
            "train_count": len(train_samples),
            "val_count": len(val_samples),
            "test_count": len(test_samples),
            "split_mode": "independent",
            "qa": {
                "train_count": len(qa_train),
                "val_count": len(qa_val),
                "test_count": len(qa_test)
            },
            "qa_from_combined": {
                "train_count": len(qa_train_combined),
                "val_count": len(qa_val_combined),
                "test_count": len(qa_test_combined)
            },
            "design": {
                "train_count": len(design_train),
                "val_count": len(design_val),
                "test_count": len(design_test)
            },
            "design_from_combined": {
                "train_count": len(design_train_combined),
                "val_count": len(design_val_combined),
                "test_count": len(design_test_combined)
            }
        }
