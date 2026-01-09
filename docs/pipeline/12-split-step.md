# Step 12 — SplitStep Design

## 章节与重点内容

- Architecture Overview：数据集切分（combined + QA/Design）
- Design Patterns：Group-aware Split
- Data Flow：`all_dedup.jsonl` → `{train,val,test}.jsonl` + `{qa,design}/*`
- Modular Detail：group_by/seed、最小样本逻辑
- Trade-offs：稳定性 vs 分布

---

## Architecture Overview

### 职责边界（Single Responsibility）

SplitStep 的职责是：将去重后的样本切分为 train/val/test，并分别输出 QA/Design 子集。

### 输入/输出（Artifacts）

- 输入：`data/intermediate/all_dedup.jsonl`
- 输出：
  - `data/final/{train,val,test}.jsonl`
  - `data/final/qa/{train,val,test}.jsonl`
  - `data/final/design/{train,val,test}.jsonl`

---

## Modular Detail

- `split.group_by` 控制分组键（默认 package），避免同一模块样本泄漏。
- 样本量过少时退化为全量训练集。
- 同时输出“combined split 与按 scenario split”的统计信息。

---

## Trade-offs

- 分组切分提高泛化性，但在样本较少时会降低验证集规模。
- QA/Design 独立切分更精准，但与 combined 分布可能不同。
