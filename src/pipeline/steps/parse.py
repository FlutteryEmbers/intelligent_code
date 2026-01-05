"""
Step 1: Parse Repository
"""
from pathlib import Path

from src.parser.java_parser import JavaParser
from src.parser.python_parser import PythonParser
from src.utils import write_json, write_jsonl, detect_license
from src.pipeline.base_step import BaseStep
from src.pipeline.helpers import should_skip_parse


class ParseStep(BaseStep):
    """Parse repository and extract code symbols."""
    
    @property
    def name(self) -> str:
        return "parse"
    
    @property
    def display_name(self) -> str:
        return "Step 1: Parsing Repository"
    
    def should_skip(self) -> tuple[bool, str]:
        """Check if can use cached symbols."""
        if self.args.skip_parse and should_skip_parse(
            self.paths["repo_meta_json"],
            self.paths["symbols_jsonl"],
            self.repo_commit
        ):
            return True, "cache_hit"
        return False, ""
    
    def execute(self) -> dict:
        """Execute parsing."""
        repo_path = Path(self.config["repo"]["path"])
        
        # Select parser based on language.name
        language_name = self.config.get("language.name", "java").lower()
        
        if language_name == "java":
            parser = JavaParser(self.config)
        elif language_name == "python":
            parser = PythonParser(self.config)
        else:
            raise ValueError(f"Unsupported language: {language_name}. Supported: java, python")
        
        self.logger.info(f"Using {language_name} parser")
        
        # Parse repository
        symbols = parser.parse_repo(repo_path, self.repo_commit)
        
        # Add license info
        license_info = detect_license(repo_path)
        
        # Build repo_meta
        repo_meta = {
            "repo_path": str(repo_path),
            "repo_commit": self.repo_commit,
            "total_symbols": len(symbols),
            "license": license_info
        }
        
        # Write outputs
        write_jsonl(self.paths["symbols_jsonl"], [s.model_dump() for s in symbols])
        write_json(self.paths["repo_meta_json"], repo_meta)
        
        self.logger.info(f"Parsed {len(symbols)} symbols")
        self.logger.info(f"License: {license_info.get('name', 'Unknown')}")
        
        return {
            "status": "success",
            "symbols_count": len(symbols),
            "license": license_info.get("name")
        }
