"""
Auto Module: Method-Level RAG Pipeline
"""
from pathlib import Path

from src.engine.auto_method_understander import AutoMethodUnderstander
from src.engine.auto_question_generator import AutoQuestionGenerator
from src.engine.auto_answer_generator import AutoAnswerGenerator
from src.utils import load_symbols_map, vector_index
from src.pipeline.base_step import BaseStep


class AutoModuleStep(BaseStep):
    """Auto module for method-level understanding and QA generation."""
    
    @property
    def name(self) -> str:
        return "auto"
    
    @property
    def display_name(self) -> str:
        """Dynamic display name based on execution mode."""
        if self.need_auto_qa and self.need_profiles_for_requirements:
            return "Auto Module: Method Profiles for Auto QA & Requirements"
        elif self.need_auto_qa:
            return "Auto Module: Method-Level Understanding & Question Generation"
        else:
            return "Auto Module: Generating Method Profiles for Requirements Enhancement"
    
    def __init__(self, config: dict, args, paths: dict, repo_commit: str):
        super().__init__(config, args, paths, repo_commit)
        
        # Determine execution needs
        auto_config = config.get("auto", {})
        requirements_config = config.get("requirements", {})
        
        # Condition 1: Auto QA is enabled via CLI and not skipping QA
        self.need_auto_qa = not args.skip_auto and not (args.skip_llm or args.skip_qa)
        
        # Condition 2: Auto Requirements needs profiles
        self.need_profiles_for_requirements = (
            not args.skip_auto and
            not args.skip_auto_requirements and
            requirements_config.get("use_method_profiles", False) and
            not (args.skip_llm or args.skip_design)
        )
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if auto module should run."""
        if not (self.need_auto_qa or self.need_profiles_for_requirements):
            if self.args.skip_auto:
                return True, "skip_flag"
            return True, "disabled"
        
        # Check if symbols file exists
        if not self.paths["symbols_jsonl"].exists():
            return True, "no_symbols"
        
        return False, ""
    
    def execute(self) -> dict:
        """Execute auto module."""
        from src.utils.config import Config
        config_instance = Config()
        config_instance.reload(self.args.config)
        
        auto_config = self.config.get("auto", {})
        artifacts = self.config.get("artifacts", {})
        
        # Prepare paths
        method_profiles_jsonl = Path(artifacts.get("method_profiles_jsonl", "data/intermediate/method_profiles.jsonl"))
        method_embeddings_jsonl = Path(artifacts.get("method_embeddings_jsonl", "data/intermediate/method_embeddings.jsonl"))
        questions_jsonl = Path(artifacts.get("questions_jsonl", "data/intermediate/questions.jsonl"))
        
        # Step A1: Method Understanding (always needed)
        max_methods = auto_config.get("max_methods", 50)
        self.logger.info(f"Step A1: Analyzing methods (max: {max_methods})")
        understander = AutoMethodUnderstander(config_instance)
        method_profiles = understander.generate_from_symbols(
            symbols_path=self.paths["symbols_jsonl"],
            repo_commit=self.repo_commit
        )
        self.logger.info(f"Generated {len(method_profiles)} method profiles")
        
        # Following steps only if Auto QA is needed
        if self.need_auto_qa:
            # Load symbols_map
            symbols_map = load_symbols_map(self.paths["symbols_jsonl"])
            
            # Step A2: Build Vector Embeddings
            embedding_model = auto_config.get("embedding_model", "nomic-embed-text")
            self.logger.info(f"Step A2: Building embeddings (model: {embedding_model})")
            vector_index.build_embeddings(
                profiles_jsonl=method_profiles_jsonl,
                embeddings_jsonl=method_embeddings_jsonl,
                embedding_model=embedding_model
            )
            self.logger.info(f"Embeddings saved to {method_embeddings_jsonl.name}")
            
            # Step A3: Generate Questions
            questions_per_method = auto_config.get("questions_per_method", 5)
            self.logger.info(f"Step A3: Generating questions ({questions_per_method} per method)")
            question_gen = AutoQuestionGenerator(config_instance)
            questions = question_gen.generate_from_profiles(
                profiles_jsonl=method_profiles_jsonl,
                symbols_map=symbols_map,
                repo_commit=self.repo_commit
            )
            self.logger.info(f"Generated {len(questions)} questions")
            
            # Step A4: Generate Answers with Vector Retrieval
            top_k_context = self.config.get("generation", {}).get("retrieval_top_k", 6)
            self.logger.info(f"Step A4: Generating answers (top_k: {top_k_context})")
            answer_gen = AutoAnswerGenerator(config_instance)
            qa_samples = answer_gen.generate_from_questions(
                questions_jsonl=questions_jsonl,
                symbols_map=symbols_map,
                repo_commit=self.repo_commit
            )
            self.logger.info(f"Generated {len(qa_samples)} auto QA samples")
            
            return {
                "status": "success",
                "method_profiles": len(method_profiles),
                "questions": len(questions),
                "qa_samples": len(qa_samples)
            }
        else:
            # Only method profiles generated
            self.logger.info("Skipping QA generation steps (only method profiles needed)")
            return {
                "status": "success",
                "method_profiles": len(method_profiles),
                "reason": "profiles_only"
            }
