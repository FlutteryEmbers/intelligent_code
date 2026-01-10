# Bug Analysis: Empty Evidence Refs in Answer Generation

Date: 2026-01-10
Status: Resolved

## 1. Issue Description

During the execution of the pipeline, the `AnswerGenerator` consistently produced `TrainingSample` objects with empty `evidence_refs`, leading to `EVIDENCE_MISSING` validation failures. The issue persisted despite the retriever correctly finding and providing relevant symbols to the prompt.

## 2. Investigation & Root Cause Analysis

We identified three compounding factors contributing to this failure:

### A. Prompt Complexity & Regression

- **Observation**: The refactored `gen_a_user.txt` instruction required the LLM to "copy the `EvidenceRef` object strictly" (JSON object structure).
- **Impact**: The 3B parameter model (Qwen2.5-3b) struggled with this strict formatting requirement while simultaneously generating complex reasoning, often dropping the field entirely or outputting malformed JSON.
- **Regression**: Comparison with the legacy `main` branch revealed that the old prompt was much simpler ("Must copy exactly") and, crucially, the **Question Generation** prompt (`gen_q_user.txt`) had lost its "Few-Shot" diverse examples, leading to lower quality input questions.

### B. The "Single Evidence Paradox"

- **Observation**: In the specific workflow of `QuestionGenerator` -> `AnswerGenerator`, the system often provided exactly **one** evidence item (the source method itself).
- **Behavior**: When presented with a single "available evidence" item, the LLM implicitly treated it as the global context. It successfully answered the question using this context but failed to "cite" it back, likely assuming it was self-evident or redundant to cite the only thing in existence.
- **Log Evidence**:

  ```
  DEBUG: Generated 1 available evidence items for prompt.
  DEBUG: Raw LLM evidence_refs: []
  ```

### C. Logic Flaw in Initial Fallback

- **Observation**: An initial code fix attempted to auto-fill if `raw_refs` was empty.
- **Failure Mode**: The LLM sometimes returned "garbage" non-empty lists (e.g., `[""]`, `[{}]`, or hallucinated IDs). The code processed these, found them invalid, and filtered them out. Because the *input* was not empty, the fallback didn't trigger, but the *output* was still empty.

## 3. Implemented Solution

We applied a multi-layered fix to ensure robustness:

### A. Prompt Simplification (Cognitive Load Reduction)

- **Action**: Modified `gen_a_user.txt` to explicitly request a **simple list of string IDs** (`["symbol_id_1"]`) instead of complex JSON objects.
- **Benefit**: Drastically reduces the formatting burden on the LLM.

### B. Robust "Single Candidate" Fallback (Code Fix)

- **Action**: Modified `AnswerGenerator._correct_evidence_refs` to move the fallback logic to the **end** of the processing chain.
- **Logic**:

  ```python
  # After processing/validation:
  if not corrected and len(symbols) == 1:
      # If we have 0 valid refs left, but context had exactly 1 trusted symbol,
      # it is logically safe to assume that symbol is the evidence.
      logger.info(f"Auto-filling single candidate: {symbols[0].symbol_id}")
      return [EvidenceRef.from_symbol(symbols[0])]
  ```

- **Benefit**: This deterministically solves the "Paradox" case. Even if the LLM hallucinates or is lazy/silent about citations, we ensure the data consistency by attributing the answer to the single provided source.

### C. Restoring Legacy Quality

- **Action**: Restored the 5 diverse, high-quality few-shot examples from the legacy `main` branch into `gen_q_user.txt`.
- **Benefit**: Ensures generated questions are varied (consistency, error handling, flow, etc.) rather than generic.

## 4. Conclusion

The issue was a combination of model capability limits (formatting) and a logical edge case (single-item context). The solution moves the burden of "citation formalism" from the probabilistic LLM to the deterministic Python logic, which is the preferred pattern for robust engineering with smaller models.
