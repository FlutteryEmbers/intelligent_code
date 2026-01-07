"""
Step 3: Design Generation (Auto Requirements + Design Samples)
"""
from src.engine.auto_requirement_generator import RequirementGenerator
from src.engine.design_generator import DesignGenerator, Requirement
from src.pipeline.base_step import BaseStep
from src.utils.config import Config


class DesignGenerationStep(BaseStep):
    """Generate design samples from requirements."""
    
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
        """Execute design generation with optional auto requirements."""
        use_auto_requirements = not self.args.skip_auto_requirements
        
        custom_requirements = None
        
        # Step 3a: Generate Auto Requirements (if enabled)
        if use_auto_requirements and not (self.args.skip_llm or self.args.skip_design):
            self.logger.info("=" * 70)
            self.logger.info(" Step 3a: Generating Auto Requirements")
            self.logger.info("=" * 70)
            
            try:
                req_gen = RequirementGenerator(Config())
                requirements_dicts = req_gen.generate_from_repo(
                    symbols_path=self.paths["symbols_jsonl"],
                    repo_commit=self.repo_commit
                )
                
                # Convert to Requirement objects
                custom_requirements = [Requirement.from_dict(req_dict) for req_dict in requirements_dicts]
                
                self.logger.info(f"Generated {len(custom_requirements)} auto requirements")
                if custom_requirements:
                    self.logger.info(f"First requirement ID: {custom_requirements[0].id}")
                else:
                    self.logger.warning("No valid requirements generated, all were rejected")
                    custom_requirements = None
            except Exception as e:
                self.logger.error(f"Auto requirement generation failed: {e}", exc_info=True)
                custom_requirements = None
        
        # Step 3b: Generate Design Samples
        self.logger.info("=" * 70)
        self.logger.info(" Step 3b: Generating Design Samples")
        self.logger.info("=" * 70)
        
        design_gen = DesignGenerator(Config())
        
        # Use auto-generated requirements or default
        if custom_requirements:
            self.logger.info(f"Using {len(custom_requirements)} auto-generated requirements")
            self.logger.info(f"Auto requirement IDs: {[req.id for req in custom_requirements[:3]]}")
            design_samples = design_gen.generate_from_repo(
                symbols_path=self.paths["symbols_jsonl"],
                repo_commit=self.repo_commit,
                requirements=custom_requirements
            )
        else:
            if use_auto_requirements:
                self.logger.warning("Auto requirements enabled but none generated, falling back to default")
            else:
                self.logger.info("Using default requirements from config")
            design_samples = design_gen.generate_from_repo(
                symbols_path=self.paths["symbols_jsonl"],
                repo_commit=self.repo_commit
            )
        
        self.logger.info(f"Generated {len(design_samples)} design samples")
        
        return {
            "status": "success",
            "auto_requirements_count": len(custom_requirements) if custom_requirements else 0,
            "samples_count": len(design_samples)
        }
