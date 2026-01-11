"""
Step 3: Design Generation (Auto Design Questions + Design Samples)
"""
from src.engine.generators.arch_design import (
    DesignGenerator,
    DesignQuestion,
    DesignQuestionGenerator,
    load_design_questions_config,
)
from src.pipeline.base_step import BaseStep
from src.utils.core.config import Config


class DesignGenerationStep(BaseStep):
    """Generate design samples from design questions."""
    
    @property
    def name(self) -> str:
        return "design_generation"
    
    @property
    def display_name(self) -> str:
        return "Step 3: Generating Design Samples"
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if design generation should be skipped."""
        if self.args.skip_llm or self.args.skip_design:
            return True, "skip_flag"
        return False, ""
    
    def execute(self) -> dict:
        """Execute design generation with optional auto design questions."""
        config_instance = Config()
        config_instance.reload(self.args.config)

        auto_enabled = not self.args.skip_question_answer
        use_auto_design_questions = auto_enabled and not self.args.skip_auto_design_questions
        design_questions_config = self.config.get("design_questions", {})
        user_design_questions_path = design_questions_config.get(
            "user_questions_path",
            "configs/design_questions.yaml",
        )
        
        custom_design_questions = None
        
        # Step 3a: Generate Auto Design Questions (if enabled)
        if use_auto_design_questions and not (self.args.skip_llm or self.args.skip_design):
            self.logger.info("=" * 70)
            self.logger.info(" Step 3a: Generating Auto Design Questions")
            self.logger.info("=" * 70)
            
            try:
                question_gen = DesignQuestionGenerator(config_instance)
                design_question_dicts = question_gen.generate_from_repo(
                    symbols_path=self.paths["symbols_jsonl"],
                    repo_commit=self.repo_commit
                )
                
                # Convert to DesignQuestion objects
                custom_design_questions = [
                    DesignQuestion.from_dict(question_dict)
                    for question_dict in design_question_dicts
                ]
                
                max_q = question_gen.max_questions
                self.logger.info(
                    f"Generated {len(custom_design_questions)}/{max_q} auto design questions"
                )
                if custom_design_questions:
                    self.logger.info(f"First design question ID: {custom_design_questions[0].id}")
                else:
                    self.logger.warning("No valid design questions generated, all were rejected")
                    custom_design_questions = None
            except Exception as e:
                self.logger.error(f"Auto design question generation failed: {e}", exc_info=True)
                custom_design_questions = None
        
        # Step 3b: Generate Design Samples
        self.logger.info("=" * 70)
        self.logger.info(" Step 3b: Generating Design Samples")
        self.logger.info("=" * 70)
        
        design_gen = DesignGenerator(config_instance)
        
        # Use auto-generated design questions or default
        if custom_design_questions:
            self.logger.info(f"Using {len(custom_design_questions)} auto-generated design questions")
            self.logger.info(f"Auto design question IDs: {[q.id for q in custom_design_questions[:3]]}")
            design_samples = design_gen.generate_from_repo(
                symbols_path=self.paths["symbols_jsonl"],
                repo_commit=self.repo_commit,
                design_questions=custom_design_questions
            )
        else:
            if use_auto_design_questions:
                self.logger.warning("Auto design questions enabled but none generated, falling back to user config")
            else:
                self.logger.info("Using user design questions from config")
            user_design_questions = load_design_questions_config(user_design_questions_path)
            design_samples = design_gen.generate_from_repo(
                symbols_path=self.paths["symbols_jsonl"],
                repo_commit=self.repo_commit,
                design_questions=user_design_questions,
            )
        
        self.logger.info(
            f"Generated {len(design_samples)}/{design_gen.stats['total']} design samples "
            f"(rejected: {design_gen.stats['failed']})"
        )
        
        return {
            "status": "success",
            "auto_design_questions_count": len(custom_design_questions) if custom_design_questions else 0,
            "samples_count": len(design_samples)
        }
