"""
基础文件读写操作

提供 JSON、JSONL、YAML 文件的读写功能，自动创建父目录。
"""
import json
from pathlib import Path
from typing import Any, Iterable

import yaml

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
        with open(path, 'wb') as f:
            for row in rows:
                f.write(orjson.dumps(row))
                f.write(b'\n')
    else:
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
        with open(path, 'ab') as f:
            f.write(orjson.dumps(row))
            f.write(b'\n')
    else:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write('\n')


def load_prompt_template(template_path: str | Path) -> str:
    """
    Load prompt template file with automatic relative path resolution.
    
    Args:
        template_path: Path to template file (absolute or relative to project root)
        
    Returns:
        Template content as string
        
    Raises:
        FileNotFoundError: If template file not found
    """
    path = Path(template_path)
    
    # Try relative path resolution if not absolute
    if not path.is_absolute():
        project_root = Path(__file__).parent.parent.parent.parent
        candidate = project_root / path
        if candidate.exists():
            path = candidate
    
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def load_yaml_file(yaml_path: str | Path) -> dict:
    """
    Load YAML file and return as dict.
    
    Args:
        yaml_path: Path to YAML file
        
    Returns:
        Parsed dict or empty dict if file doesn't exist or parse fails
    """
    path = Path(yaml_path)
    if not path.exists():
        return {}
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading YAML {path}: {e}")
        return {}


def load_yaml_list(yaml_path: str | Path, key: str | None = None) -> list:
    """
    Load list from YAML file.
    
    Args:
        yaml_path: Path to YAML file
        key: Optional key to extract list from (if None, expects top-level list)
        
    Returns:
        List or empty list if file doesn't exist or parse fails
    """
    data = load_yaml_file(yaml_path)
    
    if key:
        items = data.get(key, [])
    else:
        items = data if isinstance(data, list) else []
    
    if not isinstance(items, list):
        return []
    
    return [item for item in items if item]


def clean_llm_json_output(output: str) -> str:
    """
    Clean LLM output to extract pure JSON.
    Removes markdown code blocks, extra text, etc.
    
    Args:
        output: Raw LLM output string
        
    Returns:
        Cleaned JSON string
    """
    output = output.strip()
    
    # Remove markdown code blocks
    if output.startswith("```json"):
        output = output[7:]
    elif output.startswith("```"):
        output = output[3:]
    
    if output.endswith("```"):
        output = output[:-3]
    
    output = output.strip()
    
    # Extract JSON object (find first { and last })
    start_idx = output.find("{")
    end_idx = output.rfind("}")
    
    if start_idx != -1 and end_idx != -1:
        output = output[start_idx:end_idx+1]
    
    return _fix_json_control_chars(output)


def _fix_json_control_chars(json_str: str) -> str:
    """
    Fix common JSON errors in LLM output:
    1. Unescaped newlines/tabs inside string values.
    """
    result = []
    in_string = False
    escape_next = False
    
    for char in json_str:
        if escape_next:
            result.append(char)
            escape_next = False
            continue
            
        if char == '"':
            in_string = not in_string
            result.append(char)
        elif char == '\\':
            escape_next = True
            result.append(char)
        elif in_string:
            if char == '\n':
                result.append('\\n')
            elif char == '\t':
                result.append('\\t')
            elif char == '\r':
                result.append('\\r')
            else:
                result.append(char)
        else:
            result.append(char)
            
    return "".join(result)
