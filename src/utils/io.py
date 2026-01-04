"""
I/O utilities for JSON and JSONL file operations.
Provides functions with automatic parent directory creation.
"""
import json
from pathlib import Path
from typing import Any, Iterable

# Try to import orjson for better performance
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False


def read_json(path: Path | str) -> dict | None:
    """
    Read JSON file and return as dict.
    
    Args:
        path: Path to JSON file
        
    Returns:
        Parsed dict or None if file doesn't exist or parse fails
    """
    path = Path(path)
    if not path.exists():
        return None
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading {path}: {e}")
        return None


def write_json(path: Path | str, obj: Any, indent: int = 2) -> None:
    """
    Write object to JSON file with automatic parent directory creation.
    
    Args:
        path: Path to output JSON file
        obj: Object to serialize
        indent: JSON indentation (default: 2)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)


def read_jsonl(path: Path | str) -> list[dict]:
    """
    Read JSONL file and return list of dicts.
    
    Args:
        path: Path to JSONL file
        
    Returns:
        List of parsed dicts (empty list if file doesn't exist)
    """
    path = Path(path)
    if not path.exists():
        return []
    
    results = []
    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Error parsing line {line_num} in {path}: {e}")
                continue
    
    return results


def write_jsonl(path: Path | str, rows: Iterable[dict]) -> None:
    """
    Write iterable of dicts to JSONL file with automatic parent directory creation.
    Uses orjson if available for better performance.
    
    Args:
        path: Path to output JSONL file
        rows: Iterable of dicts to write
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if HAS_ORJSON:
        # Use orjson for faster serialization
        with open(path, 'wb') as f:
            for row in rows:
                f.write(orjson.dumps(row))
                f.write(b'\n')
    else:
        # Fallback to standard json
        with open(path, 'w', encoding='utf-8') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False))
                f.write('\n')


def append_jsonl(path: Path | str, row: dict) -> None:
    """
    Append a single dict to JSONL file with automatic parent directory creation.
    
    Args:
        path: Path to JSONL file
        row: Dict to append
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if HAS_ORJSON:
        # Use orjson for faster serialization
        with open(path, 'ab') as f:
            f.write(orjson.dumps(row))
            f.write(b'\n')
    else:
        # Fallback to standard json
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write('\n')
