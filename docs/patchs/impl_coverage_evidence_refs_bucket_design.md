# 增加 evidence_refs 计数参与难度判定（设计文档）

> 目标：在不改动现有分布模块结构的前提下，引入 evidence_refs 数量作为 **难度判定的补充信号**，减少 hard/mid 判定漂移，同时保持旧逻辑可用。

---

## 1. 现状审计（Audit）

- 现有难度判定：`coverage_tagger._infer_bucket` 仅基于 `intent + module_span` 判定。
- 现有证据控制：`design_questions.min_evidence_refs` 只约束生成阶段的最小证据，不参与**难度打标**。
- 现有分布闭环：`coverage_sampler` 依赖 `coverage.bucket` 分布；若 bucket 判定偏差，会导致抽样失真。
- 风险：在当前样本量小的情况下，`hard` 容易被 `module_span` 误判，且无法体现多证据的“复杂度”。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Validation(clean) → CoverageTagger → CoverageSampler → Merge
                      ↑
              引入 evidence_refs 计数信号
```

### 2.2 判定策略（补充信号）

- **基本原则**：保留现有 `intent + module_span` 逻辑，evidence_refs 只作为补充。
- **建议默认**：`assist` 模式（只“提升”，不“降级”）。
  - `evidence_refs >= hard_min` → bucket 至少为 hard
  - `evidence_refs >= mid_min` → bucket 至少为 mid
  - 若当前 bucket 已更高，则不变

### 2.3 适用范围

- QA 与 Design 共享同一逻辑，但**阈值可分别配置**（避免对 design 过度惩罚）。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展现有 `question_answer.coverage` 与 `design_questions.coverage`。

**配置新增（默认启用，demo 友好）：**

```yaml
question_answer:
  coverage:
    evidence_refs:
      mode: "assist"     # off | assist | strict
      mid_min: 2
      hard_min: 3

design_questions:
  coverage:
    evidence_refs:
      mode: "assist"
      mid_min: 2
      hard_min: 3
```

**旧逻辑兼容：**

- 未配置时等价于 `mode=off`，保持当前判定逻辑不变。

---

## 4. 实施环节（Phases）

1) **配置落地（默认启用 assist）**  
   在 `configs/launch.yaml` 补充 `coverage.evidence_refs`，并设置 `mode=assist`、`mid_min=2`、`hard_min=3`。

2) **打标逻辑补足（不破坏旧逻辑）**  
   在 `coverage_tagger._infer_bucket` 中读取 `evidence_refs` 数量，仅用于“提升” bucket，不做降级。

3) **报告与抽样验证**  
   重新生成 `coverage_report.json`，确认 hard/mid 分布变化可控，且抽样仍保持目标比例。

---

## 5. 决策平衡（Trade-offs）

| 选项 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| off | 维持现状 | 零风险 | 继续 hard/mid 漂移 |
| assist（推荐） | evidence_refs 仅提升 bucket | 增强多证据样本识别；不破坏旧逻辑 | 可能轻微提升 hard 比例 |
| strict | evidence_refs 可降级 bucket | 更严格分层 | 可能导致 hard 样本减少，分布偏移 |

---

## 6. 最终决策（已采用）

- **mode**：`assist`
- **阈值**：`mid_min=2`、`hard_min=3`
- **范围**：QA 与 Design 统一阈值（demo 阶段简化）

---

## 7. 影响范围（代码/配置）

- **配置**：`configs/launch.yaml`（不新增顶层模块）
- **打标**：`src/pipeline/steps/coverage_tagger.py`
- **报表**：`data/reports/coverage_report.json` 的 bucket 分布将变化
- **抽样**：`coverage_sampler` 使用 bucket 结果，抽样比例可能轻微变化

---

## 8. 必要实施清单（最小改动）

1) `configs/launch.yaml` 增加 `question_answer.coverage.evidence_refs` 与 `design_questions.coverage.evidence_refs`。  
2) `src/pipeline/steps/coverage_tagger.py`：在 `_infer_bucket` 中读取 evidence_refs 计数并执行“仅提升”规则。  
3) 可选：补一条单元测试用例，确保 `assist` 模式下 mid/hard 能被提升。  
