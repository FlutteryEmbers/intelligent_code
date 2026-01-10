"""
高级数据加载器

提供 CodeSymbol、MethodProfile 等数据模型的加载功能。
"""
import json
from pathlib import Path

from .file_ops import read_jsonl, load_yaml_file


def load_symbols_jsonl(path: Path | str) -> list:
    """
    Load CodeSymbol list from JSONL file.
    
    Args:
        path: Path to symbols JSONL file
        
    Returns:
        list[CodeSymbol]: List of code symbols
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    from src.schemas import CodeSymbol
    from src.utils.core.logger import get_logger
    logger = get_logger(__name__)
    
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Symbols file not found: {path}")
    
    symbols = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                symbol = CodeSymbol(**data)
                symbols.append(symbol)
            except Exception as e:
                logger.warning(f"Failed to parse symbol at line {line_num}: {e}")
    
    logger.info(f"Loaded {len(symbols)} symbols from {path}")
    return symbols


def load_profiles_jsonl(path: Path | str) -> list:
    """
    Load MethodProfile list from JSONL file.
    
    Args:
        path: Path to profiles JSONL file
        
    Returns:
        list[MethodProfile]: List of method profiles
    """
    from src.schemas import MethodProfile, EvidenceRef
    from src.utils.core.logger import get_logger
    logger = get_logger(__name__)
    
    path = Path(path)
    if not path.exists():
        logger.warning(f"Profiles file not found: {path}")
        return []
    
    profiles = []
    for profile_dict in read_jsonl(path):
        # 转换 evidence_refs
        evidence_refs = []
        for ref in profile_dict.get('evidence_refs', []):
            evidence_refs.append(EvidenceRef(**ref))
        profile_dict['evidence_refs'] = evidence_refs
        profiles.append(MethodProfile(**profile_dict))
    
    logger.info(f"Loaded {len(profiles)} profiles from {path}")
    return profiles


def load_architecture_constraints(path_value: str | None) -> list[str]:
    """
    Load architecture constraints from YAML file.
    
    Args:
        path_value: Path to constraints YAML file
        
    Returns:
        list[str]: List of constraint strings
    """
    from src.utils.core.logger import get_logger
    logger = get_logger(__name__)
    
    if not path_value:
        return []
    
    data = load_yaml_file(path_value)
    if not data:
        logger.warning("Architecture constraints not found: %s", path_value)
        return []
    
    if isinstance(data, dict):
        items = data.get("constraints", [])
    else:
        items = data
    
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str) and item.strip()]
