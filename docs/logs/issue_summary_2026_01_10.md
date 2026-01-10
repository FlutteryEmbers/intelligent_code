# Debugging Summary: Pipeline Robustness & Compatibility (Jan 10, 2026)

## 1. Architecture Bias (Compatibility Issue)

* **Symptom**: Design generation failed validation (`EVIDENCE_MISSING`) for repositories lacking a strict "Service" layer (e.g., `Mini-Chat-GPT`).
* **Root Cause**:
    1. `DesignGenerator` strictly required a symbol categorized as 'service' to populate the "Primary Evidence" section.
    2. `_build_grouped_context` filtered out any symbols not matching 'controller', 'service', or 'repository', resulting in empty context for flat architectures.
* **Resolution**:
  * **Evidence Fallback**: Updated logic to use 'Controller' or *any* available symbol as primary evidence if 'Service' is missing.
  * **Context Catch-All**: Added an "Other Components" section to the prompt context to capture all retrieved symbols regardless of layer type.

## 2. Pipeline Execution Errors

* **Symptom**: `AttributeError: 'DesignQuestionGenerator' object has no attribute 'max_design_questions'`.
* **Resolution**: Corrected the attribute access in `DesignGenerationStep` to use `max_questions` (matching the refactored class definition).

## 3. JSON Parsing Failures (LLM Output)

* **Symptom**: Persistent `json.decoder.JSONDecodeError: Invalid control character` or `Expecting ':' delimiter`.
* **Root Cause**: The LLM generated JSON strings containing *literal* newlines (un-escaped line breaks) inside the `answer` field, particularly when generating long-form content.
  * *Bad*: `"answer": "Line 1
Line 2"`
  * *Good*: `"answer": "Line 1\nLine 2"`
* **Resolution**: Implemented a **Lexer-based JSON Fixer** (`_fix_json_control_chars`) in `src/utils/io/file_ops.py`. This utility scans the raw LLM output and automatically escapes control characters (`\n`, `\t`, `\r`) *only* when they occur inside string values, ensuring valid JSON syntax before parsing.

## 4. Counter Visibility

* **Symptom**: User reported "Counter lost" during QA generation.
* **Resolution**: Added explicit logging in `QuestionAnswerStep` to warn if the generator returns 0 samples, helping distinguishing between "silent failure" and "logging gap".

## 5. Structure Hallucinations (Prompt Adherence)

* **Symptom**: `JSONDecodeError` persisting (`Expecting ':' delimiter` or bad array syntax) even after control-char fix.
* **Root Cause**: LLM hallucinating incorrect JSON structures despite "Minimal Structure" instructions.
    1. **Architecture Design**: For `answer`, LLM output a nested Object `{ "Header": "Content" }` instead of a single Markdown String.
    2. **QA Rule**: For `evidence_refs`, LLM output a nested array `[ [ ... ] ]` instead of an object array `[ { ... } ]`.
* **Resolution**:
  * **Design**: Updated `gen_s_user.txt` to explicitly **forbid** Object/Dictionary structures in the `answer` field.
  * **QA**: Updated `gen_a_user.txt` to explicitly **forbid** nested arrays and provide a clear `[{}, {}]` example for `evidence_refs`.

## 6. Template Formatting Crash (Regression)

* **Symptom**: `IndexError: Replacement index 0 out of range` during pipeline execution.
* **Root Cause**: In Step 5's resolution, when adding the JSON example to `gen_a_user.txt` (a Python string template), I used single curly braces `{}`. Python's `str.format()` interpreted these as placeholders expecting arguments, which were not provided.
* **Resolution**: Escaped the literal curly braces by doubling them (`{{` and `}}`) in the template file.

## 7. RAG Limitations on Fuzzy Questions (System Architecture)

* **Observation**: QA Generation fails with `EVIDENCE_MISSING` for broad/fuzzy questions (e.g., "How does the system handle partial failures?").
* **Process Analysis**:
    1. **Retriever**: Uses semantic vector search to find Top-K (e.g., 2) code symbols. For broad questions, it retrieves specific method fragments (e.g., `LoginView` error handling) that match the keywords.
    2. **Generator**: Receives these specific fragments as context. The LLM correctly infers the system behavior from these fragments (reasoning in `thought.inferences`), BUT refuses to cite them in `evidence_refs` because the prompt strictly forbids "fabrication" and requires "exact evidence". The specific fragment (micro-evidence) is often deemed insufficient by the LLM to support the broad claim (macro-answer), leading it to leave `evidence_refs` empty.
* **Risks**:
  * **Coverage Gaps**: High-level architectural questions may consistently fail validaton due to lack of explicit "system-level" evidence in the code.
  * **Bias**: The dataset may become biased towards low-level, specific questions where evidence is direct and obvious.
* **Mitigation (Future Work)**:
  * Implement **Hierarchical Retrieval**: Retrieve parent classes or module-level documentation for broad queries.
  * **Query Expansion**: Decompose fuzzy questions into multiple specific sub-queries.
  * **Evidence Relaxation**: Allow LLM to cite "representative examples" rather than requiring exhaustive proof.
