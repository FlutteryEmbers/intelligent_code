"""
Step 7: Secrets Scanning
"""
import re
from src.utils import read_jsonl, write_jsonl, scan_secrets, sanitize_text
from src.pipeline.base_step import BaseStep


class SecretsScanStep(BaseStep):
    """Scan for and filter secrets from samples."""
    
    @property
    def name(self) -> str:
        return "secrets_scan"
    
    @property
    def display_name(self) -> str:
        return "Step 7: Scanning for Secrets"

    def should_skip(self) -> tuple[bool, str]:
        """Check if secrets scan should be skipped."""
        if self.args.skip_safety:
            return True, "skip_flag"
        if not self.paths["all_dedup_jsonl"].exists():
            return True, "no_samples"
        return False, ""
    
    def execute(self) -> dict:
        """Execute secrets scanning."""
        samples = read_jsonl(self.paths["all_dedup_jsonl"])
        safety_mode = self.config.get("safety", {}).get("mode", "drop")
        blacklist_keywords = self.config.get("safety", {}).get("blacklist_keywords", [])
        if not isinstance(blacklist_keywords, list):
            blacklist_keywords = []

        clean_samples = []
        dropped_samples = []
        flagged_samples = []

        def find_blacklist_hits(text: str) -> list[str]:
            if not text:
                return []
            lowered = text.lower()
            hits = []
            for keyword in blacklist_keywords:
                if not isinstance(keyword, str) or not keyword:
                    continue
                if keyword.lower() in lowered:
                    hits.append(keyword)
            return hits

        def sanitize_blacklist(text: str) -> str:
            if not text:
                return text
            sanitized = text
            for keyword in blacklist_keywords:
                if not isinstance(keyword, str) or not keyword:
                    continue
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                sanitized = pattern.sub("[REDACTED]", sanitized)
            return sanitized

        for idx, sample in enumerate(samples):
            # Scan context and answer
            context = sample.get("context", "")
            answer = sample.get("answer", "")
            scan_text = context + "\n" + answer
            
            findings = scan_secrets(scan_text)
            blacklist_hits = find_blacklist_hits(scan_text)
            
            if findings or blacklist_hits:
                if findings:
                    self.logger.warning(f"Sample {idx}: found {len(findings)} potential secrets")
                if blacklist_hits:
                    self.logger.warning(
                        "Sample %s: found %s blacklist keyword hits",
                        idx,
                        len(blacklist_hits),
                    )

                action = safety_mode
                if safety_mode == "drop":
                    dropped_samples.append({
                        "index": idx,
                        "scenario": sample.get("scenario"),
                        "instruction": sample.get("instruction", "")[:100],
                        "findings": findings,
                        "blacklist_hits": blacklist_hits,
                        "action": "drop",
                    })
                elif safety_mode == "sanitize":
                    sample["context"] = sanitize_text(context, findings)
                    sample["answer"] = sanitize_text(answer, findings)
                    sample["context"] = sanitize_blacklist(sample["context"])
                    sample["answer"] = sanitize_blacklist(sample["answer"])
                    clean_samples.append(sample)
                    action = "sanitize"
                else:
                    clean_samples.append(sample)
                    action = "keep"

                flagged_samples.append({
                    "index": idx,
                    "scenario": sample.get("scenario"),
                    "instruction": sample.get("instruction", "")[:100],
                    "findings": findings,
                    "blacklist_hits": blacklist_hits,
                    "action": action,
                })
            else:
                clean_samples.append(sample)
        
        # Write filtered samples
        if len(clean_samples) < len(samples):
            write_jsonl(self.paths["all_dedup_jsonl"], clean_samples)
            self.logger.info(f"Filtered to {len(clean_samples)} samples (removed {len(samples) - len(clean_samples)})")
        
        # Write report
        if flagged_samples:
            write_jsonl(self.paths["secrets_dropped_jsonl"], flagged_samples)
            self.logger.info(
                "Recorded %s secret/blacklist hits to %s",
                len(flagged_samples),
                self.paths["secrets_dropped_jsonl"],
            )
        
        return {
            "status": "success",
            "mode": safety_mode,
            "filtered_count": len(samples) - len(clean_samples)
        }
