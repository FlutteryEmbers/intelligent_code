# 负样本机制（训练分布与行为变化）实现级设计

遵循 `docs/ai_rules/design/ai_design_rules.md`：增量优先、配置复用、决策透明、仅做设计。

---

## 1. 现状审计（Audit）

### 1.1 现有逻辑分布

- **问题生成**：`QuestionGenerator`/`DesignQuestionGenerator` 仅生成正向样本。
- **答案生成**：`AnswerGenerator`/`DesignGenerator` 使用统一 prompt，未区分负样本行为。
- **质量校验**：`validator.py` 以 evidence_refs 一致性为硬条件，不支持“无证据的拒答”。
- **分布控制**：`CoverageTaggerStep`/`CoverageSamplerStep` 只控制 bucket/intent，不控制正负比例。

### 1.2 冗余与耦合

- rejected 样本仅用于报告，不参与训练。
- 负样本策略若引入新的 pipeline step，容易与现有 validation/coverage 重叠。

---

## 2. 目标架构（Target Architecture）

### 2.1 更新后的逻辑流向（增量）

```
Question/Design 生成 → Negative Sampling（同阶段注入） → Answer/Design 生成
→ Validation → Coverage Tag/Sample → Merge
```

- 不新增 pipeline step；在**生成阶段**注入负样本逻辑。
- 负样本以 `quality.coverage.polarity=negative` 标记，避免破坏 schema。

### 2.2 负样本类型（建议）

- **insufficient_evidence**：证据不足，明确拒答并说明缺失点。
- **wrong_premise**：纠正前提错误，给出更正方向。
- **conflict_spec**：代码/注释冲突，提示以代码为准并说明风险。
- **ambiguous_question**：问题过于模糊，要求补充上下文。

> 目标：让模型学会“拒答/纠偏/澄清”，而非输出幻觉答案。

### 2.3 训练分布策略

- 在 `question_answer.coverage` / `design_questions.coverage` 内新增 `negative_ratio`。
- 采样时优先保证 bucket 分布，再在 bucket 内按负样本比例抽取。

---

## 3. 迁移映射（Migration Mapping）

旧 Key → 新 Key（仅新增，不新增顶层模块）

- `question_answer.coverage.negative_ratio`（新增）
- `question_answer.coverage.negative_types`（新增）
- `design_questions.coverage.negative_ratio`（新增）
- `design_questions.coverage.negative_types`（新增）
- `quality.allow_negative_without_evidence`（新增，可选）

说明：
- 默认不启用（ratio=0）以保持旧行为。
- `quality.allow_negative_without_evidence` 仅在需要“无证据拒答”时启用；否则负样本必须携带 evidence_refs。

---

## 4. 阶段性路径（Phases）

### Phase 1（影子标记）

- 仅允许用户样本标注 negative_type。
- 生成侧不注入负样本；报告中统计 negative 分布（shadow）。

### Phase 2（生成侧注入）

- 在 `QuestionGenerator`/`DesignQuestionGenerator` 内按 `negative_ratio` 采样。
- 对负样本追加 `quality.coverage.polarity=negative` 与 `negative_type` 标签。
- Answer/Design 生成时根据 `negative_type` 添加“拒答/纠偏/澄清”规则段（prompt 内注入，不新增 prompt 文件）。

### Phase 3（分布约束）

- `CoverageSamplerStep` 按 bucket 内 `negative_ratio` 进行抽样配额。
- 报告新增 polarity 分布统计（覆盖报告或质量报告中）。

---

## 5. 决策平衡（Trade-offs）

### 决策 1：负样本注入位置

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 生成阶段注入（推荐） | 改动少，与现有流程一致 | 需在生成器中增加逻辑 |
| 新增独立 step | 职责清晰 | pipeline 复杂度上升 |

### 决策 2：负样本 prompt 策略

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 同一 prompt + 规则段注入（推荐） | 文件少，改动小 | 规则表达需精准 |
| 独立 negative prompt | 易于区分行为 | 配置复杂度上升 |

### 决策 3：证据规则

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| 负样本也强制 evidence_refs（推荐） | 不破坏现有校验 | 部分拒答表达受限 |
| 允许无证据拒答 | 表达自然 | 需修改 validator 逻辑 |

### 决策 4：分布控制方式

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| bucket 内比例（推荐） | 分布更稳定 | 采样逻辑更复杂 |
| 全局比例 | 实现简单 | bucket 分布可能漂移 |

---

## 6. 配置建议（复用现有模块）

```yaml
question_answer:
  coverage:
    negative_ratio: 0.1
    negative_types: ["insufficient_evidence", "wrong_premise", "conflict_spec"]

design_questions:
  coverage:
    negative_ratio: 0.05
    negative_types: ["conflict_spec", "ambiguous_question"]

quality:
  allow_negative_without_evidence: false
```

说明：
- demo 期间建议从 0.05~0.1 起步，避免负样本过多影响模型回答风格。
- 默认 `allow_negative_without_evidence=false`，保持 evidence 约束一致性。

---

## 7. Demo/临近截至的默认策略（采用推荐决策）

基于本项目“demo 优先 + 截止临近”的约束，采用以下推荐组合：

- 决策 1：**生成阶段注入**负样本，不新增 pipeline step。
- 决策 2：**同一 prompt 规则段注入**（不新增负样本专用 prompt）。
- 决策 3：**负样本仍需 evidence_refs**（`allow_negative_without_evidence=false`）。
- 决策 4：**bucket 内比例**（在 bucket 内控制负样本比例，避免分布漂移）。

默认值建议：
- `question_answer.coverage.negative_ratio=0.1`
- `design_questions.coverage.negative_ratio=0.05`
