# Step 9 — MergeStep Design

## 章节与重点内容

- Architecture Overview：合并 QA + Design 样本
- Design Patterns：Artifact boundary、Gate-aware merge
- Data Flow：`qa_clean.jsonl`/`auto_qa_raw.jsonl` + `design_clean.jsonl`/`design_raw.jsonl` → `all_raw.jsonl`
- Modular Detail：gate_mode / allow_fallback
- Trade-offs：质量保障 vs 流水线可用性

---

## Architecture Overview

### 职责边界（Single Responsibility）

MergeStep 的职责是：把 QA 与 Design 样本合并为统一的 `all_raw.jsonl`，为后续去重与切分提供输入。

### 输入/输出（Artifacts）

- 输入（优先级：clean → raw）：
  - QA：`qa_clean.jsonl` 或 `auto_qa_raw.jsonl`
  - Design：`design_clean.jsonl` 或 `design_raw.jsonl`
- 输出：
  - `data/intermediate/all_raw.jsonl`

---

## Modular Detail

### Gate 模式

- `quality.gate_mode=gate`：必须存在 clean，否则抛错（fail-fast）。
- `quality.gate_mode=report`：允许 fallback raw（受 `allow_fallback_in_report` 控制）。
- `quality.write_clean`：控制是否写 clean 分支（Validation 中执行）。

### QA 来源选择

- Auto QA 默认来源于 `artifacts.auto_qa_raw_jsonl`（兼容 `qa_raw.jsonl`）。
- 若 clean 存在则强制使用 clean。

---

## Trade-offs

- gate 模式保证训练集质量，但对 clean 工件强依赖。
- report 模式灵活，适合 demo，但可能回放低质样本。
