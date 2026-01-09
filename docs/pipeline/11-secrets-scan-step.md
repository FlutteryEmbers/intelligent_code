# Step 11 — SecretsScanStep Design

## 章节与重点内容

- Architecture Overview：敏感信息与黑名单过滤
- Design Patterns：Rule-based Scan
- Data Flow：`all_dedup.jsonl` → (可选) 同路径回写 + `secrets_dropped.jsonl`
- Modular Detail：drop/sanitize/keep 模式
- Trade-offs：安全性 vs 样本保留率

---

## Architecture Overview

### 职责边界（Single Responsibility）

SecretsScanStep 的职责是：扫描生成样本中的密钥/敏感信息与黑名单关键词，并按配置处理。

### 输入/输出（Artifacts）

- 输入：`data/intermediate/all_dedup.jsonl`
- 输出：
  - `data/intermediate/all_dedup.jsonl`（按 mode 回写）
  - `data/reports/secrets_dropped.jsonl`（记录被标记样本）

---

## Modular Detail

### 安全模式

- `safety.mode=drop`：丢弃样本
- `safety.mode=sanitize`：替换命中内容为 `[REDACTED]`
- `safety.mode=keep`：仅记录日志与报告

### 黑名单关键词

- `safety.blacklist_keywords` 列表匹配（大小写不敏感）。
- 与 secrets scan 的结果合并处理。

---

## Trade-offs

- drop 更安全但损失样本；sanitize 保留样本但可能降低质量；keep 适合 demo/审计。
