# 健壮性与负样本（Robustness & Negative Samples）

## 🌟 核心概念：像“演练故障”一样
> 就像演习时会故意模拟故障，系统会按比例生成“反向场景”，让模型学会纠错与拒答。

## 📋 运作基石（必要元数据）

- **涉及领地 (Code Context)**：
  - `src/engine/generators/qa_rule/answer_generator.py`
  - `src/engine/generators/arch_design/design_generator.py`
  - `src/utils/data/validator.py`
  - `configs/launch.yaml`

- **执行准则 (Business Rules)**：
  - 按 `negative_ratio` 随机抽取负样本。
  - 负样本类型由 `negative_types` 决定（如证据不足、错误前提、冲突说明）。
  - 负样本会被标记为 `quality.coverage.polarity=negative` 并记录原因类型。
  - 可通过 `quality.allow_negative_without_evidence` 放宽“负样本必须有证据”的要求（默认关闭）。

- **参考证据**：
  - 负样本仍会记录证据引用，若配置允许可放宽证据要求。

## ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `question_answer.coverage.negative_ratio` | QA 负样本比例 | QA 中负样本的占比 | 0.1 |
| `question_answer.coverage.negative_types` | QA 负样本类型 | 证据不足/错误前提/冲突等 | 按风险重点选择 |
| `design_questions.coverage.negative_ratio` | Design 负样本比例 | 设计类负样本占比 | 0.05 |
| `design_questions.coverage.negative_types` | Design 负样本类型 | 冲突/模糊问题等 | 结合设计场景 |
| `quality.allow_negative_without_evidence` | 负样本证据豁免 | true 允许无证据的拒答 | demo 保持 false |

## 🛠️ 它是如何工作的（逻辑流向）

```mermaid
flowchart TD
  A[生成问题] --> B{是否抽到负样本?}
  B -- 否 --> C[正常回答]
  B -- 是 --> D[注入负样本规则]
  D --> E[输出负样本标签]
  E --> F[验证与统计]

  subgraph 业务规则
    B --> B1[negative_ratio]
    D --> D1[negative_types 规则模板]
    F --> F1[allow_negative_without_evidence]
  end
```

## 🧩 解决的痛点与带来的改变

- **以前的乱象**：样本只覆盖“顺利回答”，对错误提问没有训练价值。
- **现在的秩序**：模型能学会“指出前提错误”“拒绝胡编乱造”。

## 💡 开发者笔记

- 负样本比例是随机抽取，受 `seed` 影响，便于复现。
- 负样本依旧会进入质量校验与分布统计，保证可控。
