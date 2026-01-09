"""
Security and compliance utilities.
Provides secrets scanning and license detection.
"""
import re
from pathlib import Path
from typing import Any


# Common secret patterns
SECRET_PATTERNS = [
    # AWS Access Key
    {
        "type": "AWS_ACCESS_KEY",
        "pattern": r"AKIA[0-9A-Z]{16}",
        "description": "AWS Access Key ID"
    },
    # Private keys
    {
        "type": "PRIVATE_KEY",
        "pattern": r"-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----",
        "description": "Private Key Block"
    },
    # JWT tokens
    {
        "type": "JWT_TOKEN",
        "pattern": r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+",
        "description": "JWT Token"
    },
    # Generic API keys (common patterns)
    {
        "type": "API_KEY",
        "pattern": r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{32,})",
        "description": "API Key Assignment"
    },
    # Generic tokens
    {
        "type": "TOKEN",
        "pattern": r"(?i)token['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{32,})",
        "description": "Token Assignment"
    },
    # Generic secrets
    {
        "type": "SECRET",
        "pattern": r"(?i)secret['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})",
        "description": "Secret Assignment"
    },
    # Passwords
    {
        "type": "PASSWORD",
        "pattern": r"(?i)password['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9!@#$%^&*()_+\-=]{8,})",
        "description": "Password Assignment"
    },
    # GitHub tokens
    {
        "type": "GITHUB_TOKEN",
        "pattern": r"ghp_[a-zA-Z0-9]{36}",
        "description": "GitHub Personal Access Token"
    },
    # Slack tokens
    {
        "type": "SLACK_TOKEN",
        "pattern": r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24,}",
        "description": "Slack Token"
    },
    # Generic base64 secrets (high entropy)
    {
        "type": "BASE64_SECRET",
        "pattern": r"(?i)(?:secret|key|token|password)['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9+/]{40,}={0,2})",
        "description": "Base64 Encoded Secret"
    },
]


def scan_secrets(text: str) -> list[dict]:
    """
    Scan text for potential secrets and sensitive information.
    
    Args:
        text: Text to scan
        
    Returns:
        List of findings, each with:
        - type: Secret type (AWS_ACCESS_KEY, PRIVATE_KEY, etc.)
        - description: Human-readable description
        - start: Start position in text
        - end: End position in text
        - matched: The matched text (truncated for security)
    """
    findings = []
    
    for pattern_def in SECRET_PATTERNS:
        pattern = re.compile(pattern_def["pattern"])
        
        for match in pattern.finditer(text):
            # Get matched text and truncate for security
            matched_text = match.group(0)
            if len(matched_text) > 50:
                display_text = matched_text[:20] + "..." + matched_text[-10:]
            else:
                display_text = matched_text[:10] + "..." if len(matched_text) > 10 else matched_text
            
            findings.append({
                "type": pattern_def["type"],
                "description": pattern_def["description"],
                "start": match.start(),
                "end": match.end(),
                "matched": display_text,
                "length": len(matched_text)
            })
    
    return findings


# License file candidates
LICENSE_FILES = [
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "COPYING",
    "COPYING.txt",
    "COPYRIGHT",
    "COPYRIGHT.txt",
    "UNLICENSE",
]


# License detection patterns
LICENSE_PATTERNS = [
    {
        "name": "MIT",
        "patterns": [
            r"MIT License",
            r"Permission is hereby granted, free of charge",
        ]
    },
    {
        "name": "Apache-2.0",
        "patterns": [
            r"Apache License,?\s*Version 2\.0",
            r"Licensed under the Apache License",
        ]
    },
    {
        "name": "GPL-3.0",
        "patterns": [
            r"GNU GENERAL PUBLIC LICENSE\s*Version 3",
            r"GNU GPL v3",
        ]
    },
    {
        "name": "GPL-2.0",
        "patterns": [
            r"GNU GENERAL PUBLIC LICENSE\s*Version 2",
            r"GNU GPL v2",
        ]
    },
    {
        "name": "BSD-3-Clause",
        "patterns": [
            r"BSD 3-Clause",
            r"Redistribution and use in source and binary forms",
        ]
    },
    {
        "name": "BSD-2-Clause",
        "patterns": [
            r"BSD 2-Clause",
            r"Simplified BSD License",
        ]
    },
    {
        "name": "ISC",
        "patterns": [
            r"ISC License",
            r"Permission to use, copy, modify, and/or distribute",
        ]
    },
    {
        "name": "MPL-2.0",
        "patterns": [
            r"Mozilla Public License,?\s*Version 2\.0",
        ]
    },
    {
        "name": "LGPL-3.0",
        "patterns": [
            r"GNU LESSER GENERAL PUBLIC LICENSE\s*Version 3",
        ]
    },
    {
        "name": "LGPL-2.1",
        "patterns": [
            r"GNU LESSER GENERAL PUBLIC LICENSE\s*Version 2\.1",
        ]
    },
    {
        "name": "AGPL-3.0",
        "patterns": [
            r"GNU AFFERO GENERAL PUBLIC LICENSE\s*Version 3",
        ]
    },
    {
        "name": "Unlicense",
        "patterns": [
            r"This is free and unencumbered software released into the public domain",
        ]
    },
]


def detect_license(repo_path: Path | str) -> dict[str, Any]:
    """
    Detect license file and attempt to identify license type.
    
    Args:
        repo_path: Path to repository root
        
    Returns:
        Dict with:
        - exists: bool - Whether a license file was found
        - file: str|None - License file name
        - name: str|None - Detected license name (MIT, Apache-2.0, etc.)
        - snippet: str|None - First 400 characters of license
        - confidence: str|None - Detection confidence (high/medium/low)
    """
    repo_path = Path(repo_path)
    
    result = {
        "exists": False,
        "file": None,
        "name": None,
        "snippet": None,
        "confidence": None
    }
    
    # Try to find license file
    license_file = None
    for filename in LICENSE_FILES:
        candidate = repo_path / filename
        if candidate.exists() and candidate.is_file():
            license_file = candidate
            result["exists"] = True
            result["file"] = filename
            break
    
    if not license_file:
        return result
    
    # Read license content
    try:
        with open(license_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except IOError:
        return result
    
    # Store snippet (first 400 chars)
    result["snippet"] = content[:400].strip()
    
    # Attempt to detect license type
    matches = []
    for license_def in LICENSE_PATTERNS:
        match_count = 0
        for pattern in license_def["patterns"]:
            if re.search(pattern, content, re.IGNORECASE):
                match_count += 1
        
        if match_count > 0:
            matches.append({
                "name": license_def["name"],
                "score": match_count / len(license_def["patterns"])
            })
    
    # Select best match
    if matches:
        matches.sort(key=lambda x: x["score"], reverse=True)
        best_match = matches[0]
        result["name"] = best_match["name"]
        
        # Determine confidence
        if best_match["score"] >= 0.8:
            result["confidence"] = "high"
        elif best_match["score"] >= 0.5:
            result["confidence"] = "medium"
        else:
            result["confidence"] = "low"
    
    return result


def sanitize_text(text: str, findings: list[dict]) -> str:
    """
    Sanitize text by replacing detected secrets with placeholders.
    
    Args:
        text: Original text
        findings: List of secret findings from scan_secrets()
        
    Returns:
        Sanitized text with secrets replaced
    """
    if not findings:
        return text
    
    # Sort findings by start position (reverse order for replacement)
    sorted_findings = sorted(findings, key=lambda x: x["start"], reverse=True)
    
    result = text
    for finding in sorted_findings:
        placeholder = f"[REDACTED_{finding['type']}]"
        result = result[:finding["start"]] + placeholder + result[finding["end"]:]
    
    return result


def find_blacklist_hits(text: str, blacklist_keywords: list[str]) -> list[str]:
    """
    Find blacklist keyword hits in text.
    
    Args:
        text: Text to scan
        blacklist_keywords: List of keywords to check
        
    Returns:
        List of matched keywords
    """
    if not text or not blacklist_keywords:
        return []
    
    lowered = text.lower()
    hits = []
    for keyword in blacklist_keywords:
        if not isinstance(keyword, str) or not keyword:
            continue
        if keyword.lower() in lowered:
            hits.append(keyword)
    return hits


def sanitize_blacklist(text: str, blacklist_keywords: list[str], placeholder: str = "[REDACTED]") -> str:
    """
    Sanitize text by replacing blacklist keywords with placeholder.
    
    Args:
        text: Original text
        blacklist_keywords: List of keywords to replace
        placeholder: Replacement text (default: "[REDACTED]")
        
    Returns:
        Sanitized text with keywords replaced
    """
    if not text or not blacklist_keywords:
        return text
    
    sanitized = text
    for keyword in blacklist_keywords:
        if not isinstance(keyword, str) or not keyword:
            continue
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        sanitized = pattern.sub(placeholder, sanitized)
    return sanitized
