# 覆盖与分布设计方案（生命周期规约）

目标：在当前项目基础上构建**覆盖充分且分布合理**的数据集，满足比例：

- 80% 高频真实需求（上手、调用、配置、流程、权限、错误码、部署、变更影响）
- 15% 中等复杂（弱跨模块覆盖、规则冲突、性能/一致性权衡）
- 5% 困难样本（反直觉、坑点、历史兼容、隐含约束）

本文以生命周期逻辑组织：Upstream（生成控制）→ Processing（打标）→ Downstream（抽样与闭环），并约束标签在 Pipeline 中的流动方式。

---

## 0. 适用范围与前提

- 覆盖范围：`qa_rule` 与 `arch_design` 两类样本，数据来源包括 auto + user。
- 基础质量：依赖质量闸门（validation → clean → merge），确保证据一致性与结构稳定。
- 弱跨模块语义：跨模块仅代表“多证据覆盖”，不要求真实调用链理解。
- LLM 打标暂不启用，写入 README 的 roadmap。

---

## 1. 标签契约（跨阶段通用）

### 1.1 标签结构

使用 `TrainingSample.quality.coverage`（不改 schema）：

```json
{
  "coverage": {
    "bucket": "high|mid|hard",
    "intent": "config|flow|error|perf|compatibility|edge|...",
    "module_span": "single|multi",
    "source": "auto|user",
    "scenario": "qa_rule|arch_design"
  }
}
```

### 1.2 判定要点

- **bucket**：
  - `high`：单模块 + 常见意图
  - `mid`：多证据跨模块覆盖 + 性能/一致性权衡
  - `hard`：隐含约束/兼容性/反直觉 + 多证据覆盖
- **intent**：关键词 + evidence 路径特征（config/error/deploy/impact/perf 等）。
- **module_span**：基于 evidence_refs 的路径前缀统计，代表“多证据覆盖”。

---

## 2. Upstream（生成控制）

目标：在**生成阶段尽量贴合 80/15/5**，保证 `mid/hard` 有足够供给。

### 2.1 生成侧策略

- **上游配额**：在生成 prompt 中明确 bucket/intent，按配额生成候选问题。
- **模板库驱动**：为不同 bucket 维护模板片段，按配额取样拼接。
- **user 输入扩展**：允许 `user_questions.yaml` 显式标注 `bucket/intent`（未填则自动打标）。
- **弱跨模块约束**：`mid/hard` 优先要求 evidence_refs 跨模块覆盖。
- **先抽标签再生成**：按配置权重先抽 bucket/intent（可用随机采样且固定 seed），再驱动生成，保证分布可控。

### 2.2 高频/中等/困难样式（按场景拆分）

**QA（qa_rule）**

- **高频（80%）**：上手、配置、流程、权限、错误码、部署、变更影响（单模块证据为主）。
- **中等（15%）**：弱跨模块覆盖 + 规则冲突/性能/一致性权衡（多证据覆盖，不要求调用链）。
- **困难（5%）**：反直觉行为、历史兼容、隐含约束（仍需证据闭合）。

**Design（arch_design）**

- **高频（80%）**：基础架构约束、模块职责边界、默认流程与关键组件职责。
- **中等（15%）**：模块间协作的取舍点、规则优先级、性能与一致性权衡（多证据覆盖）。
- **困难（5%）**：历史兼容策略、隐含约束与反直觉设计决策（需要在上下文中可闭合）。

---

## 3. Processing（打标）

目标：形成**一致的覆盖标签**，供下游抽样与闭环纠偏。

### 3.1 规则打标（推荐）

- intent：关键词表 + evidence 路径特征。
- bucket：单模块/多证据覆盖 + 难度关键词映射。

### 3.2 LLM 打标（可选）

不在当前版本启用，仅写入 README roadmap。

---

## 4. Downstream（抽样与闭环）

目标：输出**稳定的 80/15/5 分布**，并驱动下一轮生成配额修正。

### 4.1 分层抽样

- 以 clean 候选池为输入做分层抽样。
- 配额不足时允许 `hard ← mid ← high` 补齐。

### 4.2 闭环纠偏

- 输出 `coverage_report`，标记缺口 bucket/intent。
- 将缺口反馈到 Upstream 的生成配额与模板策略。

---

## 5. 系统架构图（标签在 Pipeline 中的流动）

```
Question Generation
   (bucket/intent hint)
        │
        ▼
Answer/Design Generation
        │
        ▼
Validation (clean)
        │
        ▼
Coverage Tagger ──► coverage 标签写入 TrainingSample.quality.coverage
        │
        ▼
Coverage Sampler ──► 按 80/15/5 抽样 → coverage_report.json
        │
        ▼
Merge → Dedup → Split → Export
        │
        ▼
coverage_report 反馈给 Upstream 配额与模板策略
```

---

## 6. 配置扩展（不新增顶层模块）

```yaml
question_answer:
  coverage:
    mode: "hybrid"                 # upstream | downstream | hybrid
    targets: {high: 0.8, mid: 0.15, hard: 0.05}
    intent_targets:
      how_to: 0.2
      config: 0.15
      flow: 0.15
      auth: 0.1
      error: 0.15
      deploy: 0.1
      impact: 0.05
      perf: 0.05
      consistency: 0.03
      compatibility: 0.02
      edge: 0.0
    labeler: "rule"                # rule | llm
    templates_path: "configs/user_inputs/qa_templates.yaml"

design_questions:
  coverage:
    mode: "hybrid"
    targets: {high: 0.8, mid: 0.15, hard: 0.05}
    labeler: "rule"
    templates_path: "configs/user_inputs/design_templates.yaml"

artifacts:
  coverage_report_json: "data/reports/coverage_report.json"
```

---

## 7. Prompt 策略与取舍（基于“先抽标签再生成”）

目标：先由系统按配额抽取 bucket/intent，再用 prompt 约束生成内容，确保标签与语义一致。

### 7.1 关键约束（必须保留）

- **标签先行**：在生成前确定 bucket/intent（按配置权重 + 固定 seed）。
- **prompt 强约束**：即使标签已抽取，仍需在 prompt 中明确 bucket/intent 与样式要求，避免“标签对但内容跑偏”。

### 7.2 需要改动/新增的 prompt
  - `configs/prompts/qa_rule/gen_q_user.txt`
    - 增加 bucket/intent 指令 + 80/15/5 约束提示
  - `configs/prompts/arch_design/gen_q_user.txt`
    - 增加 bucket/intent 指令 + Design 样式约束
  - `configs/prompts/qa_rule/system.txt`
    - 增加 coverage 标签的输出要求或引用来源
  - `configs/prompts/arch_design/gen_s_user.txt`
    - 增加“证据闭合/多证据覆盖”的要求

### 7.3 取舍方案（按改动范围）

- **方案 A：只改问题生成 prompt（推荐）**
  - 影响：生成分布改善明显，回答侧不变
  - 风险：回答仍可能偏离 bucket 意图，需要下游抽样纠偏

### 7.4 涉及改动范围（代码/配置）

- 配置：`configs/launch.yaml` 的 `prompts.*` 路径（如新增覆盖专用 prompt）
- 生成器：`src/engine/generators/qa_rule/question_generator.py`、`src/engine/generators/arch_design/question_generator.py`
- 文档：覆盖策略与 prompt 说明同步更新

---

## 8. 关键决策与默认建议

- 配额范围：**QA/Design 分开执行 80/15/5**（默认）。
- 抽样位置：在 Dedup 前执行（保持比例稳定）。
- user 样本：计入分布，按配额平衡。
- 抽样不足：允许硬配额下调，但必须产出 coverage_report。

---

## 9. 验收指标

- 覆盖报告：bucket/intent/module_span 占比与缺口建议。
- 产出稳定性：固定输入下分布稳定（可回归）。
- 质量保证：clean 样本通过验证与 evidence 一致性校验。
