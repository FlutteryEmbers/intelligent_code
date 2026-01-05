"""
Step 2: QA Generation
"""
from src.engine.qa_generator import QAGenerator
from src.pipeline.base_step import BaseStep
from src.utils.config import Config


class QAGenerationStep(BaseStep):
    """Generate QA samples from code symbols."""
    
    @property
    def name(self) -> str:
        return "qa_generation"
    
    @property
    def display_name(self) -> str:
        return "Step 2: Generating QA Samples"
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if QA generation should be skipped."""
        auto_config = self.config.get("auto", {})
        
        # Skip if using auto module instead
        if auto_config.get("enabled", False) and not (self.args.skip_llm or self.args.skip_qa):
            return True, "auto_enabled"
        
        # Skip if flags set
        if self.args.skip_llm or self.args.skip_qa:
            return True, "skip_flag"
        
        return False, ""
    
    def execute(self) -> dict:
        """Execute QA generation."""
        qa_gen = QAGenerator(Config())
        qa_samples = qa_gen.generate_from_repo(
            symbols_path=self.paths["symbols_jsonl"],
            repo_commit=self.repo_commit
        )
        
        self.logger.info(f"Generated {len(qa_samples)} QA samples")
        
        return {
            "status": "success",
            "samples_count": len(qa_samples)
        }
