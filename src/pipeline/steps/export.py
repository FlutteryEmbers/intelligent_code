"""
Step 9: Export to SFT Format
"""
from src.utils import read_jsonl, export_sft_jsonl, export_statistics
from src.pipeline.base_step import BaseStep


class ExportStep(BaseStep):
    """Export datasets to SFT format."""
    
    @property
    def name(self) -> str:
        return "export"
    
    @property
    def display_name(self) -> str:
        return "Step 9: Exporting to SFT Format"
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if export should be skipped."""
        if self.args.skip_export:
            return True, "skip_flag"
        return False, ""
    
    def execute(self) -> dict:
        """Execute export."""
        # Export combined dataset
        if self.paths["train_jsonl"].exists():
            train_samples = read_jsonl(self.paths["train_jsonl"])
            export_sft_jsonl(train_samples, self.paths["train_sft_jsonl"])
        
        if self.paths["val_jsonl"].exists():
            val_samples = read_jsonl(self.paths["val_jsonl"])
            export_sft_jsonl(val_samples, self.paths["val_sft_jsonl"])
        
        if self.paths["test_jsonl"].exists():
            test_samples = read_jsonl(self.paths["test_jsonl"])
            export_sft_jsonl(test_samples, self.paths["test_sft_jsonl"])
        
        # Export QA dataset
        if self.paths["qa_train_jsonl"].exists():
            qa_train_samples = read_jsonl(self.paths["qa_train_jsonl"])
            if qa_train_samples:
                export_sft_jsonl(qa_train_samples, self.paths["qa_train_sft_jsonl"])
        
        if self.paths["qa_val_jsonl"].exists():
            qa_val_samples = read_jsonl(self.paths["qa_val_jsonl"])
            if qa_val_samples:
                export_sft_jsonl(qa_val_samples, self.paths["qa_val_sft_jsonl"])
        
        if self.paths["qa_test_jsonl"].exists():
            qa_test_samples = read_jsonl(self.paths["qa_test_jsonl"])
            if qa_test_samples:
                export_sft_jsonl(qa_test_samples, self.paths["qa_test_sft_jsonl"])
        
        # Export Design dataset
        if self.paths["design_train_jsonl"].exists():
            design_train_samples = read_jsonl(self.paths["design_train_jsonl"])
            if design_train_samples:
                export_sft_jsonl(design_train_samples, self.paths["design_train_sft_jsonl"])
        
        if self.paths["design_val_jsonl"].exists():
            design_val_samples = read_jsonl(self.paths["design_val_jsonl"])
            if design_val_samples:
                export_sft_jsonl(design_val_samples, self.paths["design_val_sft_jsonl"])
        
        if self.paths["design_test_jsonl"].exists():
            design_test_samples = read_jsonl(self.paths["design_test_jsonl"])
            if design_test_samples:
                export_sft_jsonl(design_test_samples, self.paths["design_test_sft_jsonl"])
        
        # Export statistics
        all_samples = train_samples + val_samples + test_samples
        stats = export_statistics(all_samples, self.paths["reports"] / "dataset_stats.json")
        
        return {
            "status": "success",
            "files": [
                str(self.paths["train_sft_jsonl"]),
                str(self.paths["val_sft_jsonl"]),
                str(self.paths["test_sft_jsonl"])
            ]
        }
