"""
Helper functions for pipeline operations.
"""
import subprocess
from pathlib import Path

from src.utils.core.logger import get_logger
from src.utils.io.file_ops import read_json

logger = get_logger(__name__)


def get_repo_commit(repo_path: Path, config_commit: str = None) -> str:
    """
    Get repository commit hash.
    
    Priority:
    1. config_commit if provided and non-empty
    2. git rev-parse HEAD if repo_path is a git repository
    3. "UNKNOWN_COMMIT" as fallback
    
    Args:
        repo_path: Path to repository
        config_commit: Commit hash from config (if any)
        
    Returns:
        Commit hash string
    """
    # Use config commit if provided
    if config_commit and config_commit.strip():
        logger.info(f"Using commit from config: {config_commit}")
        return config_commit.strip()
    
    # Try to get commit from git
    repo_path = Path(repo_path)
    git_dir = repo_path / ".git"
    
    if git_dir.exists():
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
                logger.info(f"Got commit from git: {commit[:8]}...")
                return commit
        except Exception as e:
            logger.warning(f"Failed to get git commit: {e}")
    
    # Fallback
    logger.warning("Using UNKNOWN_COMMIT as fallback")
    return "UNKNOWN_COMMIT"


def should_skip_parse(repo_meta_path: Path, symbols_path: Path, current_commit: str) -> bool:
    """
    Check if parsing can be skipped based on cache.
    
    Args:
        repo_meta_path: Path to repo_meta.json
        symbols_path: Path to symbols.jsonl
        current_commit: Current repository commit
        
    Returns:
        True if parsing can be skipped, False otherwise
    """
    # Check if files exist
    if not repo_meta_path.exists() or not symbols_path.exists():
        return False
    
    # Check if commit matches
    repo_meta = read_json(repo_meta_path)
    if not repo_meta:
        return False
    
    cached_commit = repo_meta.get("repo_commit", "")
    if cached_commit != current_commit:
        logger.info(f"Commit mismatch: cached={cached_commit[:8]}, current={current_commit[:8]}")
        return False
    
    logger.info(f"Cache hit: using existing symbols (commit={current_commit[:8]})")
    return True
