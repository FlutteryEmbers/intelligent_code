# 语义去重（Embedding 相似度）（设计文档）

> 目标：在现有 SimHash 去重基础上，新增 **embedding 相似度去重**，提升语义层面的重复过滤能力，并保持旧逻辑可并行存在。

---

## 1. 现状审计（Audit）

- 当前去重：`src/pipeline/steps/deduplication.py` 使用 SimHash（文本层面）。
- 已知问题：
  - 模板化改写、同义表述仍可通过。
  - 仅靠字符相似度难以捕捉语义重复。
- 配置现状：`dedup.simhash_bits`、`dedup.max_hamming` 已存在，但无语义去重配置。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Merge → Dedup (SimHash) → Semantic Dedup (Embedding) → Secrets Scan → Split
```

### 2.2 核心策略

- **双阶段去重**：先使用 SimHash 快速筛选，再用 embedding 相似度做语义去重。
- **最小侵入**：保留现有 SimHash 逻辑，语义去重作为可选开关。
- **可回溯**：输出语义去重映射（重复对、阈值、相似度）。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展 `dedup` 配置。

**配置新增（可选）：**

```yaml
dedup:
  simhash_bits: 64
  max_hamming: 3
  semantic:
    enabled: false
    embedding_model: "nomic-embed-text"   # 可选，默认复用 question_answer.embedding_model
    threshold: 0.92
    batch_size: 64
    max_candidates: 2000
```

**旧逻辑兼容：**

- `semantic.enabled=false` 时保持现有行为。

---

## 4. 实施路径（Phases）

1) **配置落地（默认关闭）**  
   在 `configs/launch.yaml` 添加 `dedup.semantic.*`，并保持 `enabled=false` 作为默认。

2) **语义去重实现**  
   在 `deduplication.py` 中新增 embedding 去重阶段：优先走 SimHash，语义去重仅对候选集执行。

3) **结果报告**  
   扩展 `dedup_mapping.json`，新增语义去重统计（阈值、相似度分布、drop 计数）。

4) **性能防护**  
   使用 `max_candidates` 控制候选规模，必要时引入缓存或分批计算（batch_size）。

---

## 5. 决策平衡（Trade-offs）

| 方案 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| off | 只保留 SimHash | 无新增成本 | 语义重复无法过滤 |
| semantic-on（推荐） | SimHash + Embedding | 去重质量高 | 计算成本上升 |
| semantic-only | 只用 embedding | 精度高 | 速度慢、成本高 |

---

## 6. 影响范围（代码/配置）

- **配置**：`configs/launch.yaml`（扩展 dedup）
- **去重逻辑**：`src/pipeline/steps/deduplication.py`、`src/utils/vector_index.py`（或新增 util）
- **报告**：`data/reports/dedup_mapping.json` 扩展语义去重统计

---

## 7. 最终决策（已采用）

- **embedding 模型**：默认复用 `question_answer.embedding_model`，若 `dedup.semantic.embedding_model` 明确配置则覆盖。
- **启用策略**：demo 阶段默认关闭（`semantic.enabled=false`）。
- **相似度阈值**：`threshold=0.92`。
- **批处理规模**：`batch_size=64`，`max_candidates=2000`。

---

## 8. 实施清单（最小改动）

1) `configs/launch.yaml` 增加 `dedup.semantic`，并注明 embedding_model 可复用。  
2) `src/pipeline/steps/deduplication.py` 新增 semantic 去重阶段（仅当 enabled）。  
3) `data/reports/dedup_mapping.json` 扩展语义去重统计字段。  
