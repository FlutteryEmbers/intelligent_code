# 生成侧语义约束增强（Prompt 调整）实现级设计

遵循 `docs/ai_rules/ai_design_rules.md`：增量优先、配置复用、决策透明、仅做设计。

---

## 1. 现状审计（Audit）

### 1.1 现有逻辑分布

- **问题生成**：`src/engine/generators/qa_rule/question_generator.py` 使用 `configs/prompts/qa_rule/gen_q_user.txt`。
- **设计问题生成**：`src/engine/generators/arch_design/question_generator.py` 使用 `configs/prompts/arch_design/gen_q_user.txt`。
- **覆盖分布提示**：prompt 已新增 `{coverage_bucket}` / `{coverage_intent}` 占位符，但缺少更细粒度的语义约束。

### 1.2 缺口与风险

- bucket/intent 仅作为提示，未明确“语义风格”与“结构约束”。
- 生成侧分布与风格不稳定，依赖下游抽样纠偏。
- QA 与 Design 的语义边界未明确，易出现风格漂移。

---

## 2. 目标架构（Target Architecture）

### 2.1 更新后的逻辑流向（增量）

```
Bucket/Intent 抽取 → Prompt 语义约束增强 → LLM 生成 → 现有解析与校验
```

- 不新增 pipeline step，仅增强 prompt 内容与配置。
- coverage prompt 为可选项，缺失时回退旧 prompt，支持并行对比与回滚。

### 2.2 语义约束目标

- **分布一致性**：每个 bucket 的问题/设计题“语义可判别”。
- **风格稳定性**：QA 偏“问题与解释”，Design 偏“约束与取舍”。
- **弱跨模块约束**：多证据覆盖而非调用链推理。
- **强度分层**：`high` 采用弱约束，`mid/hard` 采用强约束（同一 prompt 内分层）。

---

## 3. 迁移映射（Migration Mapping）

不新增顶层模块，仅扩展 `prompts.*`：

- 旧 Key → 新 Key
  - `prompts.question_answer.question_generation`
    → `prompts.question_answer.coverage_generation`（可选）
  - `prompts.design_questions_generation`
    → `prompts.design.coverage_generation`（可选）

兼容策略：未配置 coverage prompt 时使用原始 prompt。

---

## 4. 阶段性路径（Phases）

### Phase 1（影子配置）

- 新增 coverage prompt 文件，但默认不启用。
- 保留旧 prompt 作为 fallback（缺失则回退）。

### Phase 2（逻辑重定向）

- 开启 `coverage_generation` 路径（单一 coverage prompt）。
- 观察分布报告与 rejected 波动。

### Phase 3（旧逻辑弃用）

- 当分布稳定且风格一致后，将旧 prompt 降级为备用。

---

## 5. 决策平衡（Trade-offs）

### 决策 1：是否新增覆盖专用 prompt

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 新增 coverage prompt（推荐） | 便于 A/B 对比与回滚 | 维护成本上升 |


### 决策 2：约束强度

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 强约束（推荐） | 语义更可控 | 可能降低多样性 |
| 弱约束 | 多样性高 | 分布漂移风险 |

新增配置项来决定约束强度（不新增顶层模块）：

- `question_answer.coverage.constraint_strength: strong | weak | hybrid`
- `design_questions.coverage.constraint_strength: strong | weak | hybrid`

说明：
- `strong/weak`：整体统一强度。
- `hybrid`：按 `coverage_bucket` 分层（high=弱，mid/hard=强）。

补充（demo 低改动兼顾方案）：
- 使用 `constraint_strength=hybrid`，在同一套 prompt 内按 `coverage_bucket` 分层。
- 仅需修改 prompt 文本，配置落在现有 coverage 节点。

### 决策 3：覆盖 prompt 的颗粒度

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 单一 coverage prompt（推荐） | 维护成本低 | 需要 prompt 内部规则清晰 |
| 多 prompt（按 bucket/intent 拆分） | 语义更可控 | 文件数量上升、配置复杂 |

### 决策 4：约束注入位置

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| prompt 内显式规则段（推荐） | 可读、可回归 | 可能降低生成多样性 |
| 仅依赖占位符引导 | 改动小 | 约束强度不稳定 |

### 决策 5：fallback 策略

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| coverage prompt 缺失时回退旧 prompt（推荐） | 不中断流程 | 覆盖约束可能失效 |
| 缺失即报错 | 约束可控 | Demo 运行摩擦增加 |

### 决策 6：QA/Design 风格边界

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 只在 prompt 文字区分（推荐） | 实施简单 | 依赖模型遵循 |
| 输出结构化标签（如 type/bucket 片段） | 可检验 | 可能影响解析与格式稳定 |

---

## 6. 配置建议（复用现有模块）

```yaml
prompts:
  question_answer:
    question_generation: "configs/prompts/qa_rule/gen_q_user.txt"
    coverage_generation: "configs/prompts/qa_rule/gen_q_user.txt"
    coverage:
      constraint_strength: "hybrid"  # strong | weak | hybrid
  design_questions_generation: "configs/prompts/arch_design/gen_q_user.txt"
  design:
    coverage_generation: "configs/prompts/arch_design/gen_q_user.txt"
  design_questions:
    coverage:
      constraint_strength: "hybrid"
```

说明：
- `coverage_generation` 可选，缺失时回退 `question_generation` / `design_questions_generation`。
- 单一 coverage prompt，不按 bucket/intent 拆分为多个文件。

---

## 7. 验收标准

- coverage_report 中 bucket/intent 分布更稳定。
- QA/Design 风格差异可通过人工抽样快速辨识。
- rejected 比例不显著上升（或可解释）。

---

## 8. Demo/临近截至的默认策略

基于“demo 为主 + 交付临近”，选择**最小改动且可回滚**的组合：

- 决策 1：**新增 coverage prompt（但默认不启用）**，保留旧 prompt 作为稳定基线。
- 决策 2：**通过配置决定强/弱**（`constraint_strength=hybrid`，在同一 prompt 内按 `coverage_bucket` 分层）。
- 决策 3：**单一 coverage prompt**（减少文件/配置数量）。
- 决策 4：**prompt 内显式规则段**（更可控，便于人工抽查）。
- 决策 5：**缺失则回退旧 prompt**（不中断流程）。
- 决策 6：**仅在 prompt 文字区分 QA/Design 风格**（不引入结构化输出变更）。

说明：以上默认策略以稳定性与低风险为优先，若后续需要更强约束，可逐步启用“多 prompt 拆分”与“结构化标签”。
