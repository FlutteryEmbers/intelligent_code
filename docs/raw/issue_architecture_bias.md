# Issue: Architecture Bias in Design Generation

## Problem Description

The initial implementation of `DesignGenerator` and `Retriever` was strictly biased towards **Layered Architectures** (specifically Controller-Service-Repository patterns common in web frameworks like Django/Spring).

### Symptoms

In repositories that do not follow this strict layering (e.g., flat scripts, libraries, or micro-frameworks):

1. **Validation Failures**: `EVIDENCE_MISSING` or `EVIDENCE_SYMBOL_NOT_FOUND`.
    - Cause: The generator logic specifically looked for a `Service` layer symbol to populate the "Primary Evidence" section of the prompt. If no service was found (count = 0), this section became empty, and the LLM consequently failed to generate valid `evidence_refs`.
2. **Empty Context**:
    - Cause: `_build_grouped_context` strictly filtered symbols into `['controller', 'service', 'repository']`. Any symbol not matching these profiles was silently discarded, potentially resulting in an empty or insufficient context window for the LLM.

## Resolution (2026-01-10)

The pipeline has been generalized to support **Generic Python Architectures**:

1. **Evidence Fallback Strategy**:
    - If a `Service` layer symbol is not found, the generator now falls back to using `Controller`, `Repository`, or *any* retrieved relevant symbol as the "Primary Evidence".
    - This ensures the LLM always has a reference anchor to cite, regardless of the code structure.

2. **Context Catch-All**:
    - `_build_grouped_context` now includes an **"Other Components"** section.
    - Any relevant symbol that does not fit into the standard layers is included here, ensuring no retrieved information is lost.

## Verification

- Validated against `Mini-Chat-GPT` (which lacks explicit Service layers) and confirmed successful generation and validation (passing the previously failing checks).
