"""
Step 7: Secrets Scanning
"""
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
    
    def execute(self) -> dict:
        """Execute secrets scanning."""
        samples = read_jsonl(self.paths["all_dedup_jsonl"])
        safety_mode = self.config.get("safety", {}).get("mode", "drop")
        
        clean_samples = []
        dropped_samples = []
        
        for idx, sample in enumerate(samples):
            # Scan context and answer
            context = sample.get("context", "")
            answer = sample.get("answer", "")
            scan_text = context + "\n" + answer
            
            findings = scan_secrets(scan_text)
            
            if findings:
                self.logger.warning(f"Sample {idx}: found {len(findings)} potential secrets")
                
                if safety_mode == "drop":
                    # Drop this sample
                    dropped_samples.append({
                        "index": idx,
                        "scenario": sample.get("scenario"),
                        "instruction": sample.get("instruction", "")[:100],
                        "findings": findings
                    })
                elif safety_mode == "sanitize":
                    # Sanitize and keep
                    sample["context"] = sanitize_text(context, findings)
                    sample["answer"] = sanitize_text(answer, findings)
                    clean_samples.append(sample)
            else:
                clean_samples.append(sample)
        
        # Write filtered samples
        if len(clean_samples) < len(samples):
            write_jsonl(self.paths["all_dedup_jsonl"], clean_samples)
            self.logger.info(f"Filtered to {len(clean_samples)} samples (removed {len(samples) - len(clean_samples)})")
        
        # Write report
        if dropped_samples:
            write_jsonl(self.paths["secrets_dropped_jsonl"], dropped_samples)
            self.logger.info(f"Dropped {len(dropped_samples)} samples with secrets")
        
        return {
            "status": "success",
            "mode": safety_mode,
            "filtered_count": len(samples) - len(clean_samples)
        }
