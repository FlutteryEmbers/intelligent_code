"""
Step A1: Method Understanding
"""
from src.engine.auto_method_understander import AutoMethodUnderstander
from src.pipeline.base_step import BaseStep
from src.utils.config import Config


class MethodUnderstandingStep(BaseStep):
    """Generate method profiles from symbols."""

    @property
    def name(self) -> str:
        return "method_understanding"

    @property
    def display_name(self) -> str:
        return "Step A1: Method Understanding"

    def should_skip(self) -> tuple[bool, str]:
        """Check if method understanding should be skipped."""
        enabled = self.config.get("method_understanding", {}).get("enabled", True)
        if not enabled:
            return True, "disabled"

        qa_config = self.config.get("question_answer", {})
        build_embeddings_in_user_mode = qa_config.get("build_embeddings_in_user_mode", False)
        auto_enabled = not self.args.skip_question_answer

        if not auto_enabled and not build_embeddings_in_user_mode:
            return True, "user_mode_no_embeddings"

        if self.args.skip_llm:
            return True, "skip_flag"

        if not self.paths["symbols_jsonl"].exists():
            return True, "no_symbols"

        return False, ""

    def execute(self) -> dict:
        """Execute method understanding."""
        config_instance = Config()
        config_instance.reload(self.args.config)

        understander = AutoMethodUnderstander(config_instance)
        method_profiles = understander.generate_from_symbols(
            symbols_path=self.paths["symbols_jsonl"],
            repo_commit=self.repo_commit,
        )

        self.logger.info(f"Generated {len(method_profiles)} method profiles")

        return {
            "status": "success",
            "method_profiles": len(method_profiles),
        }
