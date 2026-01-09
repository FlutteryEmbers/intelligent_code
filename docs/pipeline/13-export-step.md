# Step 13 — ExportStep Design

## 章节与重点内容

- Architecture Overview：导出 SFT 格式与统计
- Design Patterns：Adapter/Formatter
- Data Flow：`*.jsonl` → `*_sft.jsonl` + `dataset_stats.json`
- Modular Detail：combined + QA/Design
- Trade-offs：格式统一 vs 细粒度控制

---

## Architecture Overview

### 职责边界（Single Responsibility）

ExportStep 的职责是：将切分后的样本转换为 SFT 训练格式，并输出基础统计。

### 输入/输出（Artifacts）

- 输入：`data/final/{train,val,test}.jsonl` 以及 `data/final/{qa,design}/*`
- 输出：
  - `data/final/*_sft.jsonl`
  - `data/reports/dataset_stats.json`

---

## Modular Detail

- Combined 与 QA/Design 三套数据独立导出。
- 如果某个 split 为空，则跳过对应导出。

---

## Trade-offs

- 统一导出逻辑减少配置复杂度，但格式扩展需要在 export 统一处理。
