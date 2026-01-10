"""
Question/Answer Module: Method-Level RAG Pipeline
"""
from pathlib import Path

from src.engine.generators.qa_rule import QuestionGenerator, AnswerGenerator, load_user_questions_config
from src.utils.data.validator import load_symbols_map
from src.utils.retrieval import vector_index
from src.pipeline.base_step import BaseStep


class QuestionAnswerStep(BaseStep):
    """Question/answer generation module."""
    
    @property
    def name(self) -> str:
        return "question_answer"
    
    @property
    def display_name(self) -> str:
        """Dynamic display name based on execution mode."""
        if self.need_qa and self.need_profiles_for_design_questions:
            if self.auto_enabled:
                return "Question/Answer: Method Profiles for Auto QA & Design Questions"
            return "Question/Answer: User QA + Method Profiles for Design Questions"
        if self.need_qa:
            if self.auto_enabled:
                return "Question/Answer: Method Profiles & Question Generation"
            return "Question/Answer: User Questions to QA Generation"
        return "Question/Answer: Method Profiles for Design Question Enhancement"
    
    def __init__(self, config: dict, args, paths: dict, repo_commit: str):
        super().__init__(config, args, paths, repo_commit)
        
        # Determine execution needs
        qa_config = config.get("question_answer", {})
        design_questions_config = config.get("design_questions", {})
        self.auto_enabled = not args.skip_question_answer
        self.need_qa = not (args.skip_llm or args.skip_qa)
        self.build_embeddings_in_user_mode = qa_config.get(
            "build_embeddings_in_user_mode",
            False,
        )
        self.max_questions = qa_config.get("max_questions")
        self.user_questions_path = qa_config.get(
            "user_questions_path",
            "configs/user_questions.yaml"
        )
        
        # Condition: Auto design questions need profiles
        self.need_profiles_for_design_questions = (
            self.auto_enabled and
            not args.skip_auto_design_questions and
            design_questions_config.get("use_method_profiles", False) and
            not (args.skip_llm or args.skip_design)
        )
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if auto module should run."""
        if not (self.need_qa or self.need_profiles_for_design_questions):
            if self.args.skip_question_answer or self.args.skip_qa or self.args.skip_llm:
                return True, "skip_flag"
            return True, "disabled"
        
        # Check if symbols file exists
        if not self.paths["symbols_jsonl"].exists():
            return True, "no_symbols"
        
        return False, ""
    
    def execute(self) -> dict:
        """Execute auto module."""
        from src.utils.core.config import Config
        config_instance = Config()
        config_instance.reload(self.args.config)
        
        qa_config = self.config.get("question_answer", {})
        artifacts = self.config.get("artifacts", {})
        
        # Prepare paths
        method_profiles_jsonl = Path(artifacts.get("method_profiles_jsonl", "data/intermediate/method_profiles.jsonl"))
        method_embeddings_jsonl = Path(artifacts.get("method_embeddings_jsonl", "data/intermediate/method_embeddings.jsonl"))
        questions_jsonl = Path(artifacts.get("questions_jsonl", "data/intermediate/auto_questions/questions.jsonl"))
        
        # Following steps only if QA is needed
        if self.need_qa:
            # Load symbols_map
            symbols_map = load_symbols_map(self.paths["symbols_jsonl"])
            
            if self.auto_enabled:
                if not method_profiles_jsonl.exists():
                    self.logger.error(
                        "Method profiles not found: %s (enable method_understanding or run without --skip-question-answer)",
                        method_profiles_jsonl,
                    )
                    return {
                        "status": "failed",
                        "reason": "missing_method_profiles",
                    }
                # Step A2: Build Vector Embeddings
                embedding_model = qa_config.get("embedding_model", "nomic-embed-text")
                self.logger.info(f"Step A2: Building embeddings (model: {embedding_model})")
                vector_index.build_embeddings(
                    profiles_jsonl=method_profiles_jsonl,
                    embeddings_jsonl=method_embeddings_jsonl,
                    embedding_model=embedding_model
                )
                self.logger.info(f"Embeddings saved to {method_embeddings_jsonl.name}")
                
                # Step A3: Generate Questions
                questions_per_method = qa_config.get("questions_per_method", 5)
                max_questions = qa_config.get("max_questions")
                self.logger.info(f"Step A3: Generating questions ({questions_per_method} per method, max: {max_questions or 'unlimited'})")
                question_gen = QuestionGenerator(config_instance)
                questions = question_gen.generate_from_profiles(
                    profiles_jsonl=method_profiles_jsonl,
                    symbols_map=symbols_map,
                    repo_commit=self.repo_commit
                )
                potential = question_gen.stats['total_profiles'] * questions_per_method
                self.logger.info(
                    f"Generated {len(questions)}/{max_questions or potential} questions "
                    f"(potential: {potential} from {question_gen.stats['total_profiles']} profiles)"
                )
            else:
                if self.build_embeddings_in_user_mode:
                    if not method_profiles_jsonl.exists():
                        self.logger.error(
                            "Method profiles not found: %s (enable method_understanding to build embeddings)",
                            method_profiles_jsonl,
                        )
                        return {
                            "status": "failed",
                            "reason": "missing_method_profiles",
                        }
                    embedding_model = qa_config.get("embedding_model", "nomic-embed-text")
                    self.logger.info(
                        "Step A2: Building embeddings for user questions (model: %s)",
                        embedding_model,
                    )
                    vector_index.build_embeddings(
                        profiles_jsonl=method_profiles_jsonl,
                        embeddings_jsonl=method_embeddings_jsonl,
                        embedding_model=embedding_model,
                    )
                    self.logger.info(f"Embeddings saved to {method_embeddings_jsonl.name}")

                # Step A3: Load user questions
                self.logger.info("Step A3: Loading user questions from config")
                questions = load_user_questions_config(
                    config_path=self.user_questions_path,
                    repo_commit=self.repo_commit
                )
                if self.max_questions is not None and len(questions) > self.max_questions:
                    self.logger.info(
                        "Truncating user questions to max_questions=%s (from %s)",
                        self.max_questions,
                        len(questions),
                    )
                    questions = questions[: self.max_questions]
                missing_refs = sum(1 for q in questions if not q.evidence_refs)
                if missing_refs:
                    self.logger.warning(
                        "User questions missing evidence_refs: %s (vector search requires embeddings)",
                        missing_refs,
                    )
                questions_jsonl.parent.mkdir(parents=True, exist_ok=True)
                with open(questions_jsonl, 'w', encoding='utf-8') as f:
                    for question in questions:
                        f.write(question.model_dump_json() + '\n')
                if questions:
                    self.logger.info(f"Loaded {len(questions)} user questions")
                else:
                    self.logger.warning("No user questions loaded; questions.jsonl will be empty")
            
            # Step A4: Generate Answers with Vector Retrieval
            top_k_context = self.config.get("core", {}).get(
                "retrieval_top_k",
                self.config.get("generation", {}).get("retrieval_top_k", 6),
            )
            self.logger.info(f"Step A4: Generating answers (top_k: {top_k_context})")
            answer_gen = AnswerGenerator(config_instance)
            qa_samples = answer_gen.generate_from_questions(
                questions_jsonl=questions_jsonl,
                symbols_map=symbols_map,
                repo_commit=self.repo_commit
            )
            total_q = answer_gen.stats['total_questions']
            if total_q == 0:
                self.logger.warning("AnswerGenerator processed 0 questions. Check questions.jsonl content.")
            else:
                self.logger.info(f"Generated {len(qa_samples)}/{total_q} QA samples (rejected: {answer_gen.stats['failed']})")
            
            return {
                "status": "success",
                "method_profiles": 0,
                "questions": len(questions),
                "qa_samples": len(qa_samples)
            }
        else:
            # No QA needed in this step
            self.logger.info("Skipping QA generation steps (no QA requested)")
            return {
                "status": "success",
                "reason": "no_qa",
            }
