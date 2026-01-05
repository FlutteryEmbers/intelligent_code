"""
Base class for pipeline steps.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from src.utils import get_logger

logger = get_logger(__name__)


class BaseStep(ABC):
    """Base class for all pipeline steps."""
    
    def __init__(self, config: dict, args: Any, paths: dict, repo_commit: str):
        """
        Initialize step.
        
        Args:
            config: Pipeline configuration
            args: Command line arguments
            paths: Dictionary of file paths
            repo_commit: Repository commit hash
        """
        self.config = config
        self.args = args
        self.paths = paths
        self.repo_commit = repo_commit
        self.logger = get_logger(self.__class__.__name__)
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Step name for logging and summary."""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name for console output."""
        pass
    
    def should_skip(self) -> tuple[bool, str]:
        """
        Check if this step should be skipped.
        
        Returns:
            Tuple of (should_skip: bool, reason: str)
        """
        return False, ""
    
    @abstractmethod
    def execute(self) -> dict:
        """
        Execute the step.
        
        Returns:
            Step result dictionary with status and other info
        """
        pass
    
    def run(self) -> dict:
        """
        Run the step with skip check and error handling.
        
        Returns:
            Step result dictionary
        """
        # Check if should skip
        should_skip, reason = self.should_skip()
        if should_skip:
            self.logger.info(f"Skipping {self.display_name}: {reason}")
            return {"status": "skipped", "reason": reason}
        
        # Log step start
        self.logger.info("=" * 70)
        self.logger.info(f" {self.display_name}")
        self.logger.info("=" * 70)
        
        # Execute step with error handling
        try:
            result = self.execute()
            result.setdefault("status", "success")
            return result
        except Exception as e:
            self.logger.error(f"{self.display_name} failed: {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}
