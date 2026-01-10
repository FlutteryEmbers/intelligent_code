"""
Dataset splitting utilities with group-based stratification.
Prevents data leakage by ensuring related samples stay in the same split.
"""
import random
from pathlib import Path
from typing import Any
from collections import defaultdict

from src.schemas import CodeSymbol


def extract_package_from_qualified_name(qualified_name: str) -> str:
    """
    Extract package prefix from Java qualified name.
    
    Examples:
        com.foo.bar.UserService.createUser -> com.foo.bar
        com.example.Main.main -> com.example
        HelloWorld.main -> (empty string for default package)
    
    Args:
        qualified_name: Fully qualified name (package.Class.method)
        
    Returns:
        Package prefix (empty string if no package)
    """
    if not qualified_name:
        return ""
    
    # Split by dots
    parts = qualified_name.split(".")
    
    # If only one part (e.g., "HelloWorld"), no package
    if len(parts) <= 1:
        return ""
    
    # Remove last two parts (Class.method or just Class)
    # Keep everything else as package
    # Heuristic: assume at least 2 parts for class.method
    if len(parts) >= 3:
        # com.foo.bar.Class.method -> com.foo.bar
        return ".".join(parts[:-2])
    else:
        # foo.Class -> foo (or empty if just Class.method)
        return parts[0] if len(parts) == 2 else ""


def extract_directory_from_path(file_path: str) -> str:
    """
    Extract directory from file path.
    
    Examples:
        src/main/java/com/foo/UserService.java -> src/main/java/com/foo
        com/example/Main.java -> com/example
        Main.java -> (empty string for root)
    
    Args:
        file_path: File path
        
    Returns:
        Directory path (empty string if in root)
    """
    if not file_path:
        return ""
    
    path = Path(file_path)
    parent = path.parent
    
    return str(parent) if str(parent) != "." else ""


def get_sample_group_key(
    sample: dict,
    symbols_map: dict[str, CodeSymbol],
    group_by: str = "package"
) -> str:
    """
    Extract group key from sample for stratified splitting.
    
    Args:
        sample: TrainingSample dict
        symbols_map: symbol_id -> CodeSymbol mapping
        group_by: Grouping strategy ("package" or "path")
        
    Returns:
        Group key string
    """
    # Normalize path separators for cross-platform compatibility
    from .validator import normalize_path_separators
    
    # Get first evidence ref
    thought = sample.get("thought", {})
    evidence_refs = thought.get("evidence_refs", [])
    
    if not evidence_refs:
        # No evidence refs - use special group
        return "_NO_EVIDENCE_"
    
    # Get first evidence symbol_id
    first_ref = evidence_refs[0]
    symbol_id = first_ref.get("symbol_id", "")
    
    # Normalize symbol_id
    normalized_symbol_id = normalize_path_separators(symbol_id) if symbol_id else ""
    
    if not normalized_symbol_id or normalized_symbol_id not in symbols_map:
        return "_UNKNOWN_SYMBOL_"
    
    # Get symbol
    symbol = symbols_map[normalized_symbol_id]
    
    # Extract group key based on strategy
    if group_by == "package":
        # Use package from qualified_name
        group_key = extract_package_from_qualified_name(symbol.qualified_name)
        if not group_key:
            group_key = "_DEFAULT_PACKAGE_"
    elif group_by == "path":
        # Use directory from file_path
        group_key = extract_directory_from_path(symbol.file_path)
        if not group_key:
            group_key = "_ROOT_PATH_"
    else:
        raise ValueError(f"Unknown group_by strategy: {group_by}")
    
    return group_key


def group_split_samples(
    samples: list[dict],
    symbols_map: dict[str, CodeSymbol],
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    seed: int = 42,
    group_by: str = "package",
    min_groups_for_grouping: int = 5
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Split samples into train/val/test sets with group-based stratification.
    Ensures that samples from the same group (package or directory) stay together.
    
    Args:
        samples: List of TrainingSample dicts
        symbols_map: symbol_id -> CodeSymbol mapping
        train_ratio: Ratio for training set (default: 0.8)
        val_ratio: Ratio for validation set (default: 0.1)
        test_ratio: Ratio for test set (default: 0.1)
        seed: Random seed for reproducibility
        group_by: Grouping strategy - "package" or "path"
        min_groups_for_grouping: Minimum groups for group-based split
        
    Returns:
        Tuple of (train_samples, val_samples, test_samples)
    """
    # Validate ratios
    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 0.001:
        raise ValueError(f"Ratios must sum to 1.0, got {total_ratio}")
    
    if not samples:
        return [], [], []
    
    # Group samples by key
    groups = defaultdict(list)
    for sample in samples:
        group_key = get_sample_group_key(sample, symbols_map, group_by)
        groups[group_key].append(sample)
    
    print(f"Grouped {len(samples)} samples into {len(groups)} groups by {group_by}")
    
    # Convert to list of (group_key, samples) tuples
    group_list = list(groups.items())

    # Fallback to sample-level split when groups are too few
    if len(group_list) < min_groups_for_grouping:
        random.seed(seed)
        shuffled = list(samples)
        random.shuffle(shuffled)

        n = len(shuffled)
        train_count = int(n * train_ratio)
        val_count = int(n * val_ratio)

        # Ensure at least 1 sample in each split if possible
        if n >= 3:
            if train_count == 0:
                train_count = 1
            if val_count == 0:
                val_count = 1
            if train_count + val_count >= n:
                train_count = max(1, n - 2)
                val_count = 1

        train_samples = shuffled[:train_count]
        val_samples = shuffled[train_count:train_count + val_count]
        test_samples = shuffled[train_count + val_count:]

        print("=" * 70)
        print(" Dataset Split Summary")
        print("=" * 70)
        print(f"Split strategy: sample-level fallback (groups={len(group_list)}, threshold={min_groups_for_grouping})")
        print(f"Total samples: {len(samples)}")
        print()
        print(f"Train: {len(train_samples)} samples ({len(train_samples)/len(samples):.2%})")
        print(f"Val:   {len(val_samples)} samples ({len(val_samples)/len(samples):.2%})")
        print(f"Test:  {len(test_samples)} samples ({len(test_samples)/len(samples):.2%})")
        print("=" * 70)

        return train_samples, val_samples, test_samples
    
    # Shuffle groups
    random.seed(seed)
    random.shuffle(group_list)
    
    # Calculate split points based on group count
    num_groups = len(group_list)
    train_groups = int(num_groups * train_ratio)
    val_groups = int(num_groups * val_ratio)
    
    # Ensure at least 1 group in each split if possible
    if num_groups == 1:
        # Only 1 group - put everything in train
        train_groups = 1
        val_groups = 0
    elif num_groups == 2:
        # 2 groups - split between train and test
        train_groups = 1
        val_groups = 0
    elif num_groups >= 3:
        # 3+ groups - ensure at least 1 in each split
        if train_groups == 0:
            train_groups = 1
        if val_groups == 0:
            val_groups = 1
        if train_groups + val_groups >= num_groups:
            # Adjust to ensure test gets at least 1 group
            train_groups = max(1, num_groups - 2)
            val_groups = 1
    
    # Split groups
    train_group_list = group_list[:train_groups]
    val_group_list = group_list[train_groups:train_groups + val_groups]
    test_group_list = group_list[train_groups + val_groups:]
    
    # Flatten back to samples
    train_samples = []
    for _, group_samples in train_group_list:
        train_samples.extend(group_samples)
    
    val_samples = []
    for _, group_samples in val_group_list:
        val_samples.extend(group_samples)
    
    test_samples = []
    for _, group_samples in test_group_list:
        test_samples.extend(group_samples)
    
    # Print summary
    print("=" * 70)
    print(" Dataset Split Summary")
    print("=" * 70)
    print(f"Split strategy: {group_by}")
    print(f"Total samples: {len(samples)}")
    print(f"Total groups: {num_groups}")
    print()
    print(f"Train: {len(train_samples)} samples from {len(train_group_list)} groups "
          f"({len(train_samples)/len(samples):.2%})")
    print(f"Val:   {len(val_samples)} samples from {len(val_group_list)} groups "
          f"({len(val_samples)/len(samples):.2%})")
    print(f"Test:  {len(test_samples)} samples from {len(test_group_list)} groups "
          f"({len(test_samples)/len(samples):.2%})")
    print("=" * 70)
    
    return train_samples, val_samples, test_samples


def analyze_split_distribution(
    train_samples: list[dict],
    val_samples: list[dict],
    test_samples: list[dict],
    symbols_map: dict[str, CodeSymbol],
    group_by: str = "package"
) -> dict[str, Any]:
    """
    Analyze distribution of samples across splits.
    
    Args:
        train_samples: Training samples
        val_samples: Validation samples
        test_samples: Test samples
        symbols_map: symbol_id -> CodeSymbol mapping
        group_by: Grouping strategy used
        
    Returns:
        Dict with distribution statistics
    """
    def get_groups(samples):
        groups = set()
        for sample in samples:
            group_key = get_sample_group_key(sample, symbols_map, group_by)
            groups.add(group_key)
        return groups
    
    train_groups = get_groups(train_samples)
    val_groups = get_groups(val_samples)
    test_groups = get_groups(test_samples)
    
    # Check for leakage
    train_val_overlap = train_groups & val_groups
    train_test_overlap = train_groups & test_groups
    val_test_overlap = val_groups & test_groups
    
    total_samples = len(train_samples) + len(val_samples) + len(test_samples)
    all_groups = train_groups | val_groups | test_groups
    
    return {
        "total_samples": total_samples,
        "total_groups": len(all_groups),
        "train": {
            "samples": len(train_samples),
            "groups": len(train_groups),
            "ratio": len(train_samples) / total_samples if total_samples > 0 else 0
        },
        "val": {
            "samples": len(val_samples),
            "groups": len(val_groups),
            "ratio": len(val_samples) / total_samples if total_samples > 0 else 0
        },
        "test": {
            "samples": len(test_samples),
            "groups": len(test_groups),
            "ratio": len(test_samples) / total_samples if total_samples > 0 else 0
        },
        "leakage": {
            "train_val_overlap": len(train_val_overlap),
            "train_test_overlap": len(train_test_overlap),
            "val_test_overlap": len(val_test_overlap),
            "has_leakage": len(train_val_overlap) > 0 or len(train_test_overlap) > 0 or len(val_test_overlap) > 0
        }
    }
