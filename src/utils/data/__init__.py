"""
Data processing and validation sub-package.
Provides validator, dedup, splitter, sampling, and coverage utilities.
"""
from .validator import (
    normalize_path_separators,
    load_symbols_map,
    load_symbols_list,
    validate_sample_obj,
    validate_dataset,
    validate_file,
)
from .dedup import (
    simhash,
    hamming_distance,
    dedup_jsonl_by_simhash,
    dedup_jsonl_by_semantic,
    calculate_dataset_diversity,
)
from .splitter import (
    extract_package_from_qualified_name,
    extract_directory_from_path,
    get_sample_group_key,
    group_split_samples,
    analyze_split_distribution,
)
from .sampling import (
    reservoir_sampling,
    stratified_sample_by_scenario,
    sample_by_coverage,
)
from .coverage import (
    INTENT_KEYWORDS,
    HARD_KEYWORDS,
    BUCKETS,
    DEFAULT_TARGETS,
    FALLBACK_CHAIN,
    infer_intent,
    infer_module_span,
    infer_bucket,
    apply_evidence_bucket,
    compute_distribution,
    compute_multi_distributions,
    normalize_targets,
    desired_counts,
)

__all__ = [
    # validator
    "normalize_path_separators",
    "load_symbols_map",
    "load_symbols_list",
    "validate_sample_obj",
    "validate_dataset",
    "validate_file",
    # dedup
    "simhash",
    "hamming_distance",
    "dedup_jsonl_by_simhash",
    "dedup_jsonl_by_semantic",
    "calculate_dataset_diversity",
    # splitter
    "extract_package_from_qualified_name",
    "extract_directory_from_path",
    "get_sample_group_key",
    "group_split_samples",
    "analyze_split_distribution",
    # sampling
    "reservoir_sampling",
    "stratified_sample_by_scenario",
    "sample_by_coverage",
    # coverage
    "INTENT_KEYWORDS",
    "HARD_KEYWORDS",
    "BUCKETS",
    "DEFAULT_TARGETS",
    "FALLBACK_CHAIN",
    "infer_intent",
    "infer_module_span",
    "infer_bucket",
    "apply_evidence_bucket",
    "compute_distribution",
    "compute_multi_distributions",
    "normalize_targets",
    "desired_counts",
]
