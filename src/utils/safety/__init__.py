"""
Safety sub-package.
Provides security scanning and compliance utilities.
"""
from .scanner import (
    SECRET_PATTERNS,
    LICENSE_FILES,
    LICENSE_PATTERNS,
    scan_secrets,
    detect_license,
    sanitize_text,
    find_blacklist_hits,
    sanitize_blacklist,
)

__all__ = [
    "SECRET_PATTERNS",
    "LICENSE_FILES",
    "LICENSE_PATTERNS",
    "scan_secrets",
    "detect_license",
    "sanitize_text",
    "find_blacklist_hits",
    "sanitize_blacklist",
]
