# Step 10 — DeduplicationStep Design

## 章节与重点内容

- Architecture Overview：去重策略（SimHash + 语义去重可选）
- Design Patterns：Deterministic Dedup、Artifact boundary
- Data Flow：`all_raw.jsonl` → `all_dedup.jsonl` + `dedup_mapping.json`
- Modular Detail：simhash 参数、semantic 开关
- Trade-offs：速度 vs 相似性质量

---

## Architecture Overview

### 职责边界（Single Responsibility）

DeduplicationStep 的职责是：对合并样本去重，降低重复训练样本比例。

### 输入/输出（Artifacts）

- 输入：`data/intermediate/all_raw.jsonl`
- 输出：
  - `data/intermediate/all_dedup.jsonl`
  - `data/reports/dedup_mapping.json`

---

## Modular Detail

### SimHash 去重（默认）

- `dedup.simhash_bits` / `dedup.max_hamming` 控制强度。
- 写入 `dedup_mapping.json` 统计。

### 语义去重（可选）

- `dedup.semantic.enabled=true` 启用。
- 使用 embeddings 计算相似度并合并结果回写到 `dedup_mapping.json.semantic`。

---

## Trade-offs

- SimHash 速度快、可解释，但对语义近似重复不敏感。
- 语义去重质量更高，但需要 embeddings 依赖与更高成本。
