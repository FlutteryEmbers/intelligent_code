# TODO: Gate Mode Integrity and Evidence Anchoring
>
> Date: 2026-01-11
> Source: docs/logs/2026-01-11_workflow_integrity_design_audit_report.md

## Scope

- Enforce strict gate-mode behavior for design samples.
- Remove or constrain evidence auto-fill paths that can bypass validation.
- Make auto-filled evidence visible and rejectable in gate mode.

## Non-goals

- Add LLM-as-a-Judge implementation.
- Redesign prompt templates beyond evidence requirements.

## Change List (Concrete)

1) Gate-mode merge enforcement (Design)
- File: `src/pipeline/steps/merge.py`
- Change: When `gate_mode == "gate"` and `write_clean == true`, treat missing `design_clean_jsonl` as a hard error (match QA behavior).
- Rationale: Prevent raw design samples from entering downstream when validation fails.

2) Disable evidence auto-fill in gate mode
- File: `src/engine/generators/qa_rule/answer_generator.py`
- Change: Remove or guard the fallback that auto-fills `evidence_refs` when only one symbol is available.
- Gate behavior: If `gate_mode == "gate"`, do not auto-fill; rely on LLM output and validation.

3) Avoid forced evidence overwrite during question generation
- File: `src/engine/generators/qa_rule/question_generator.py`
- Change: Do not blindly overwrite `evidence_refs` with `default_ref` in gate mode. If LLM output is missing, let validation fail or require explicit evidence output.

4) Avoid silent evidence fill in design question generation
- File: `src/engine/generators/arch_design/question_generator.py`
- Change: Remove or gate-guard fallback to `evidence_pool[0]` when evidence_refs is missing.

5) Tag auto-filled evidence for auditability
- Files: `src/engine/generators/qa_rule/answer_generator.py`, `src/engine/generators/qa_rule/question_generator.py`, `src/engine/generators/arch_design/question_generator.py`
- Change: When auto-fill is still allowed (report mode), add `quality.evidence_autofill=true` (or similar) to the sample metadata.

6) Gate-mode validation for auto-filled evidence
- File: `src/utils/data/validator.py`
- Change: If `quality.evidence_autofill == true` and `quality.gate_mode == "gate"` (or config gate_mode is gate), mark as failed with a specific error code.

## Fix Plan

Phase 1: Strict gate enforcement
- Implement change (1).
- Add or update unit tests for merge gate behavior (if tests exist).

Phase 2: Evidence auto-fill control
- Implement changes (2), (3), (4).
- Add metadata tag for auto-fill (5).
- Update validation to reject auto-fill in gate mode (6).

Phase 3: Observability
- Update coverage/reporting to count auto-filled samples (optional).

## Acceptance Criteria

- Gate mode never merges design raw samples when clean is missing.
- Samples with missing or auto-filled evidence are rejected in gate mode.
- Report mode can still keep auto-fill with explicit tagging.

## Validation Steps

- Run pipeline with `quality.gate_mode=gate` and confirm:
  - If `design_clean_jsonl` is missing, pipeline fails early.
  - Samples with auto-filled evidence do not appear in clean outputs.
- Run pipeline with `quality.gate_mode=report` and confirm:
  - Auto-filled samples carry `quality.evidence_autofill=true`.

## Risks

- Stricter gate mode may reduce output volume; ensure upstream prompts produce evidence_refs.
- Some existing datasets may fail validation until prompts are tuned.

