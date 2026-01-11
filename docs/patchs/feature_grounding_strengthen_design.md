# Grounding 强化（检索策略变化，影响最大）实现级设计

遵循 `docs/ai_rules/design/ai_design_rules.md`：增量优先、配置复用、决策透明、仅做设计。

---

## 1. 现状审计（Audit）

### 1.1 现有检索路径

- **QA 生成**：`AnswerGenerator` 优先使用问题自带 `evidence_refs`；缺失时回退到向量检索（`vector_index.search`）。
- **Design 生成**：`DesignGenerator` 使用轻量级 RAG（候选过滤 + 关键词检索），并在 user prompt 中附证据。
- **Method Understanding**：影响 `method_profiles.jsonl`，间接影响 QA 检索质量。

### 1.2 现有风险

- 缺失或无效 `evidence_refs` 时，QA 只能靠向量检索，噪声和漂移风险高。
- Design 的检索仍偏启发式，不稳定于跨模块场景。
- 质量门以 `evidence_refs` 一致性为硬条件，检索失真会直接导致 rejected 增加。

---

## 2. 目标架构（Target Architecture）

### 2.1 更新后的逻辑流向（增量，采用 hybrid）

```
Evidence 优先 → 稳健检索（多策略候选池） → 证据对齐过滤 → 上下文构建
```

- 不新增 pipeline step，仍在现有 Generator 内升级检索策略。
- 采用 **hybrid**：`evidence_refs` 优先，其次向量检索补齐。

### 2.2 强化目标（与采用策略对齐）

- **降低漂移**：检索结果与问题意图更一致。
- **减少 rejected**：证据对齐失败率下降。
- **分布稳定**：负样本与高难样本检索不失真。

---

## 3. 迁移映射（Migration Mapping）

复用现有模块，新增配置项，不新增顶层模块：

- `question_answer.retrieval`（新增节）
  - `mode: "hybrid" | "vector_only" | "symbol_only"`
  - `min_score: 0.2`（向量召回阈值）
  - `fallback_top_k: 6`（回退检索数量）
- `design_questions.retrieval`（新增节）
  - `mode: "hybrid" | "symbol_only"`
  - `fallback_top_k: 8`

说明：
- 默认仍使用原有行为（hybrid），仅通过参数改善稳定性。

---

## 4. 阶段性路径（Phases，采用顺序）

### Phase 1（影子统计：先做统计，不改变选择）

- 仅统计检索命中率、score 分布与 evidence 对齐失败原因。
- 不改变选择逻辑，输出报告字段。

### Phase 2（弱约束：启用低阈值与回退 top_k）

- 启用 `min_score` 与 `fallback_top_k`，对低相关候选降权。
- 不影响既有 evidence_refs 优先级。

### Phase 3（强约束：仅用于定位问题）

- 在 `mode=symbol_only` 或 `mode=vector_only` 的情况下强制单策略，便于定位问题。

---

## 5. 决策平衡（Trade-offs，采用推荐选择）

### 决策 1：检索策略（采用 hybrid）

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| hybrid（采用） | 稳定性与召回平衡 | 逻辑稍复杂 |
| vector_only | 实现简单 | evidence 对齐风险高 |
| symbol_only | 证据一致性高 | 召回不足 |

### 决策 2：score 阈值（采用低阈值）

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 低阈值（采用） | 召回高 | 噪声增加 |
| 高阈值 | 噪声低 | 容易空召回 |

### 决策 3：多策略候选池（采用 evidence + vector）

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| evidence + vector（采用） | 对齐最稳 | 处理流程增加 |
| 单策略 | 简单 | 漂移风险高 |

---

## 6. 配置建议（复用现有模块）

```yaml
question_answer:
  retrieval:
    mode: "hybrid"
    min_score: 0.2
    fallback_top_k: 6

design_questions:
  retrieval:
    mode: "hybrid"
    fallback_top_k: 8
```

---

## 7. Demo/临近截至的默认策略

基于“demo 优先 + 截止临近”：

- 采用 `mode=hybrid`，仅引入 `min_score` 与 `fallback_top_k`。
- 不改 pipeline 结构，仅增强生成器内部检索逻辑。
- 先影子统计，再启用阈值过滤。
