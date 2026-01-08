"""
Step 5: Merge Samples
"""
from pathlib import Path

from src.utils import read_jsonl, write_jsonl
from src.pipeline.base_step import BaseStep


class MergeStep(BaseStep):
    """Merge QA and design samples into single file."""
    
    @property
    def name(self) -> str:
        return "merge"
    
    @property
    def display_name(self) -> str:
        return "Step 5: Merging Samples"
    
    def execute(self) -> dict:
        """Execute merge."""
        all_samples = []
        quality_cfg = self.config.get("quality", {})
        gate_mode = quality_cfg.get("gate_mode", "report")
        write_clean = bool(quality_cfg.get("write_clean", True))
        allow_fallback = bool(quality_cfg.get("allow_fallback_in_report", True))
        artifacts = self.config.get("artifacts", {})
        qa_clean_path = Path(
            artifacts.get(
                "qa_clean_jsonl",
                self.paths.get("qa_clean_jsonl", "data/intermediate/clean/qa_clean.jsonl"),
            )
        )
        design_clean_path = Path(
            artifacts.get(
                "design_clean_jsonl",
                self.paths.get("design_clean_jsonl", "data/intermediate/clean/design_clean.jsonl"),
            )
        )
        
        # Determine which QA source to use
        qa_paths = []
        if not (self.args.skip_llm or self.args.skip_qa):
            artifacts = self.config.get("artifacts", {})
            qa_paths.append(
                Path(artifacts.get("auto_qa_raw_jsonl", "data/intermediate/auto_qa_raw.jsonl"))
            )
            qa_paths.append(self.paths.get("qa_raw_jsonl"))
            # De-duplicate paths while preserving order.
            seen = set()
            qa_paths = [p for p in qa_paths if p and not (p in seen or seen.add(p))]
            if qa_paths:
                self.logger.info(
                    "Using QA sources: %s",
                    ", ".join(p.name for p in qa_paths),
                )
        
        # Load QA samples
        if qa_paths:
            raw_available = any(p.exists() for p in qa_paths if p)
            if write_clean and qa_clean_path.exists():
                qa_paths = [qa_clean_path]
                self.logger.info("Using QA clean samples: %s", qa_clean_path.name)
            elif raw_available:
                if write_clean and gate_mode == "gate":
                    raise FileNotFoundError(
                        f"QA clean file not found in gate mode: {qa_clean_path}"
                    )
                if gate_mode == "report" and not allow_fallback and write_clean:
                    raise FileNotFoundError(
                        f"QA clean file missing and fallback disabled: {qa_clean_path}"
                    )
                if write_clean:
                    self.logger.warning(
                        "QA clean file missing, falling back to raw sources in report mode."
                    )
            else:
                self.logger.warning("No QA samples found in configured sources")
                qa_paths = []

            loaded_any = False
            for qa_path in qa_paths:
                if qa_path.exists():
                    qa_samples = read_jsonl(qa_path)
                    all_samples.extend(qa_samples)
                    self.logger.info(f"Loaded {len(qa_samples)} QA samples from {qa_path.name}")
                    loaded_any = True
                else:
                    self.logger.warning(f"QA samples not found: {qa_path}")
            if not loaded_any:
                self.logger.warning("No QA samples loaded from configured sources")
        
        # Load design samples
        design_path = self.paths["design_raw_jsonl"]
        if write_clean and design_clean_path.exists():
            design_path = design_clean_path
            self.logger.info("Using design clean samples: %s", design_clean_path.name)
        elif Path(design_path).exists():
            if write_clean and gate_mode == "gate":
                raise FileNotFoundError(
                    f"Design clean file not found in gate mode: {design_clean_path}"
                )
            if gate_mode == "report" and not allow_fallback and write_clean:
                raise FileNotFoundError(
                    f"Design clean file missing and fallback disabled: {design_clean_path}"
                )
            if write_clean:
                self.logger.warning(
                    "Design clean file missing, falling back to raw samples in report mode."
                )

        if Path(design_path).exists():
            design_samples = read_jsonl(design_path)
            all_samples.extend(design_samples)
            self.logger.info(f"Loaded {len(design_samples)} design samples")
        else:
            self.logger.warning(f"Design samples not found: {design_path}")
        
        # Write merged samples
        if all_samples:
            write_jsonl(self.paths["all_raw_jsonl"], all_samples)
            self.logger.info(f"Merged {len(all_samples)} samples to {self.paths['all_raw_jsonl']}")
        
        return {
            "status": "success",
            "total_samples": len(all_samples)
        }
