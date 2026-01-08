"""
Deduplication utilities using simhash.
Provides near-duplicate detection for training samples.
"""
import hashlib
from pathlib import Path
from typing import Any

try:
    import ollama
except ImportError:
    ollama = None

from .io import read_jsonl, write_jsonl, write_json


def simhash(text: str, bits: int = 64) -> int:
    """
    Calculate simhash for given text using shingle-based approach.
    
    Args:
        text: Input text to hash
        bits: Number of bits for simhash (default: 64)
        
    Returns:
        Integer simhash value
    """
    if not text:
        return 0
    
    # Use character-level 3-grams (shingles)
    shingles = []
    text_lower = text.lower()
    
    # Generate word-level tokens
    words = text_lower.split()
    shingles.extend(words)
    
    # Generate character-level 3-grams for additional granularity
    for i in range(len(text_lower) - 2):
        shingles.append(text_lower[i:i+3])
    
    if not shingles:
        return 0
    
    # Initialize bit vector
    v = [0] * bits
    
    # Process each shingle
    for shingle in shingles:
        # Hash the shingle
        h = int(hashlib.md5(shingle.encode('utf-8')).hexdigest(), 16)
        
        # Update bit vector
        for i in range(bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    
    # Generate final simhash
    fingerprint = 0
    for i in range(bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    
    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    """
    Calculate hamming distance between two hash values.
    
    Args:
        hash1: First hash value
        hash2: Second hash value
        
    Returns:
        Hamming distance (number of differing bits)
    """
    xor = hash1 ^ hash2
    distance = 0
    while xor:
        distance += 1
        xor &= xor - 1  # Remove rightmost 1-bit
    return distance


def dedup_jsonl_by_simhash(
    input_jsonl: Path | str,
    output_jsonl: Path | str,
    mapping_json: Path | str,
    bits: int = 64,
    seed: int = 42,
    max_hamming: int = 3
) -> None:
    """
    Deduplicate JSONL file using simhash with hamming distance threshold.
    
    Args:
        input_jsonl: Input JSONL file path
        output_jsonl: Output JSONL file path (deduplicated)
        mapping_json: Output JSON file with deduplication mapping
        bits: Number of bits for simhash (default: 64)
        seed: Random seed (unused but kept for API consistency)
        max_hamming: Maximum hamming distance for near-duplicates (default: 3)
    """
    input_jsonl = Path(input_jsonl)
    output_jsonl = Path(output_jsonl)
    mapping_json = Path(mapping_json)
    
    # Read input samples
    samples = read_jsonl(input_jsonl)
    
    if not samples:
        print(f"No samples found in {input_jsonl}")
        write_jsonl(output_jsonl, [])
        write_json(mapping_json, {
            "kept": [],
            "dropped": [],
            "pairs": []
        })
        return
    
    # Track kept samples and their hashes
    kept_samples = []
    kept_hashes = []
    kept_indices = []
    
    # Track dropped samples
    dropped_indices = []
    pairs = []  # (dropped_index, kept_index) tuples
    
    print(f"Deduplicating {len(samples)} samples...")
    print(f"Simhash bits: {bits}, Max hamming distance: {max_hamming}")
    
    # Process each sample
    for idx, sample in enumerate(samples):
        # Extract key for comparison
        instruction = sample.get("instruction", "")
        answer = sample.get("answer", "")
        key = instruction + "\n" + answer
        
        # Calculate simhash
        sample_hash = simhash(key, bits=bits)
        
        # Check for near-duplicates
        is_duplicate = False
        matched_idx = -1
        
        for kept_idx, kept_hash in zip(kept_indices, kept_hashes):
            distance = hamming_distance(sample_hash, kept_hash)
            
            if distance <= max_hamming:
                # Near-duplicate found
                is_duplicate = True
                matched_idx = kept_idx
                break
        
        if is_duplicate:
            # Drop this sample
            dropped_indices.append(idx)
            pairs.append({
                "dropped_index": idx,
                "kept_index": matched_idx,
                "hamming_distance": distance
            })
        else:
            # Keep this sample
            kept_samples.append(sample)
            kept_hashes.append(sample_hash)
            kept_indices.append(idx)
    
    # Write output
    write_jsonl(output_jsonl, kept_samples)
    
    # Write mapping
    mapping = {
        "input_file": str(input_jsonl),
        "output_file": str(output_jsonl),
        "total_input": len(samples),
        "total_kept": len(kept_samples),
        "total_dropped": len(dropped_indices),
        "dedup_rate": len(dropped_indices) / len(samples) if samples else 0.0,
        "config": {
            "bits": bits,
            "max_hamming": max_hamming
        },
        "kept": kept_indices,
        "dropped": dropped_indices,
        "pairs": pairs
    }
    
    write_json(mapping_json, mapping)
    
    # Print summary
    print("=" * 70)
    print(" Deduplication Summary")
    print("=" * 70)
    print(f"Input samples: {len(samples)}")
    print(f"Kept samples: {len(kept_samples)}")
    print(f"Dropped samples: {len(dropped_indices)}")
    print(f"Deduplication rate: {mapping['dedup_rate']:.2%}")
    print()
    print(f"Output file: {output_jsonl}")
    print(f"Mapping file: {mapping_json}")
    print("=" * 70)


def calculate_dataset_diversity(
    jsonl_path: Path | str,
    bits: int = 64
) -> dict[str, Any]:
    """
    Calculate diversity metrics for a dataset using simhash.
    
    Args:
        jsonl_path: Path to JSONL file
        bits: Number of bits for simhash
        
    Returns:
        Dict with diversity metrics:
        - total: Total samples
        - unique_hashes: Number of unique simhashes
        - avg_hamming: Average hamming distance between consecutive samples
        - min_hamming: Minimum hamming distance
        - max_hamming: Maximum hamming distance
    """
    jsonl_path = Path(jsonl_path)
    samples = read_jsonl(jsonl_path)
    
    if len(samples) < 2:
        return {
            "total": len(samples),
            "unique_hashes": len(samples),
            "avg_hamming": None,
            "min_hamming": None,
            "max_hamming": None
        }
    
    # Calculate hashes
    hashes = []
    for sample in samples:
        instruction = sample.get("instruction", "")
        answer = sample.get("answer", "")
        key = instruction + "\n" + answer
        h = simhash(key, bits=bits)
        hashes.append(h)
    
    # Count unique hashes
    unique_hashes = len(set(hashes))
    
    # Calculate pairwise hamming distances
    hamming_distances = []
    for i in range(len(hashes) - 1):
        dist = hamming_distance(hashes[i], hashes[i + 1])
        hamming_distances.append(dist)
    
    return {
        "total": len(samples),
        "unique_hashes": unique_hashes,
        "uniqueness_rate": unique_hashes / len(samples),
        "avg_hamming": sum(hamming_distances) / len(hamming_distances),
        "min_hamming": min(hamming_distances),
        "max_hamming": max(hamming_distances)
    }


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    if len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


def _build_semantic_text(sample: dict) -> str:
    instruction = sample.get("instruction", "")
    answer = sample.get("answer", "")
    return f"{instruction}\n{answer}".strip()


def _embed_texts(texts: list[str], embedding_model: str) -> list[list[float] | None]:
    if ollama is None:
        return [None for _ in texts]
    embeddings: list[list[float] | None] = []
    for text in texts:
        try:
            response = ollama.embeddings(
                model=embedding_model,
                prompt=text,
            )
            embeddings.append(response.get("embedding"))
        except Exception:
            embeddings.append(None)
    return embeddings


def dedup_jsonl_by_semantic(
    input_jsonl: Path | str,
    output_jsonl: Path | str,
    embedding_model: str,
    threshold: float = 0.92,
    batch_size: int = 64,
    max_candidates: int = 2000,
    mapping_json: Path | str | None = None,
) -> dict[str, Any]:
    input_jsonl = Path(input_jsonl)
    output_jsonl = Path(output_jsonl)

    samples = read_jsonl(input_jsonl)
    if not samples:
        mapping = {
            "input_file": str(input_jsonl),
            "output_file": str(output_jsonl),
            "total_input": 0,
            "total_kept": 0,
            "total_dropped": 0,
            "dedup_rate": 0.0,
            "skipped": True,
            "reason": "empty",
            "config": {
                "embedding_model": embedding_model,
                "threshold": threshold,
                "batch_size": batch_size,
                "max_candidates": max_candidates,
            },
            "kept": [],
            "dropped": [],
            "pairs": [],
        }
        write_jsonl(output_jsonl, [])
        if mapping_json:
            write_json(Path(mapping_json), mapping)
        return mapping

    if ollama is None:
        mapping = {
            "input_file": str(input_jsonl),
            "output_file": str(output_jsonl),
            "total_input": len(samples),
            "total_kept": len(samples),
            "total_dropped": 0,
            "dedup_rate": 0.0,
            "skipped": True,
            "reason": "ollama_missing",
            "config": {
                "embedding_model": embedding_model,
                "threshold": threshold,
                "batch_size": batch_size,
                "max_candidates": max_candidates,
            },
            "kept": list(range(len(samples))),
            "dropped": [],
            "pairs": [],
        }
        write_jsonl(output_jsonl, samples)
        if mapping_json:
            write_json(Path(mapping_json), mapping)
        return mapping

    kept_samples: list[dict] = []
    kept_embeddings: list[list[float] | None] = []
    kept_indices: list[int] = []
    dropped_indices: list[int] = []
    pairs: list[dict[str, Any]] = []

    texts = [_build_semantic_text(sample) for sample in samples]
    embeddings: list[list[float] | None] = []
    for i in range(0, len(texts), max(1, batch_size)):
        batch = texts[i:i + batch_size]
        embeddings.extend(_embed_texts(batch, embedding_model))

    for idx, (sample, embedding) in enumerate(zip(samples, embeddings)):
        start = 0
        if max_candidates and len(kept_embeddings) > max_candidates:
            start = len(kept_embeddings) - max_candidates

        best_score = 0.0
        best_keep_idx = -1
        for i in range(start, len(kept_embeddings)):
            candidate = kept_embeddings[i]
            if candidate is None or embedding is None:
                continue
            score = _cosine_similarity(embedding, candidate)
            if score > best_score:
                best_score = score
                best_keep_idx = kept_indices[i]
            if score >= threshold:
                break

        if best_score >= threshold and best_keep_idx != -1:
            dropped_indices.append(idx)
            pairs.append({
                "dropped_index": idx,
                "kept_index": best_keep_idx,
                "similarity": round(best_score, 4),
            })
            continue

        kept_samples.append(sample)
        kept_embeddings.append(embedding)
        kept_indices.append(idx)

    write_jsonl(output_jsonl, kept_samples)

    mapping = {
        "input_file": str(input_jsonl),
        "output_file": str(output_jsonl),
        "total_input": len(samples),
        "total_kept": len(kept_samples),
        "total_dropped": len(dropped_indices),
        "dedup_rate": len(dropped_indices) / len(samples) if samples else 0.0,
        "skipped": False,
        "config": {
            "embedding_model": embedding_model,
            "threshold": threshold,
            "batch_size": batch_size,
            "max_candidates": max_candidates,
        },
        "kept": kept_indices,
        "dropped": dropped_indices,
        "pairs": pairs,
    }

    if mapping_json:
        write_json(Path(mapping_json), mapping)

    return mapping
