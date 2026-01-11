# 推理链路质量（Reasoning Trace Logic）

## 🌟 核心概念：像“工作日志”一样
> 就像项目复盘要有过程记录，系统要求答案不仅有结论，还要留下“为什么这么判断”的可读线索。

## 📋 运作基石（必要元数据）

- **涉及领地 (Code Context)**：
  - `src/utils/data/validator.py`
  - `src/engine/generators/qa_rule/answer_generator.py`
  - `src/engine/generators/arch_design/design_generator.py`
  - `configs/launch.yaml`
  - `configs/prompts/qa_rule/gen_a_user.txt`
  - `configs/prompts/arch_design/gen_s_user.txt`
  - `configs/prompts/common/arch_constraints.yaml`

- **执行准则 (Business Rules)**：
  - 输出必须包含结构化“推理记录”（observations / inferences / assumptions / evidence_refs）。
  - 可启用“推理记录结构校验”“证据锚定校验”“答案一致性校验”。
  - 可启用“反例对比”提示（Rejected Alternatives）。
  - 可注入架构约束清单，提醒答案遵守已有设计限制。

- **参考证据**：
  - trace 中的证据引用必须可追溯到 `symbols.jsonl`。

## ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `quality.trace_rules.mode` | 推理记录校验模式 | warning / reject | demo 用 warning |
| `quality.trace_rules.require_trace_structure` | 结构校验 | 必须有 observations/inferences | true |
| `quality.trace_rules.require_evidence_anchor` | 证据锚定 | 要求 trace 中有证据引用 | true |
| `quality.trace_rules.require_answer_alignment` | 结论一致性 | 要求答案能被 trace 支撑 | 按需开启 |
| `quality.trace_rules.min_observations` | 最少观察数 | 防止空白 trace | 1 |
| `quality.trace_rules.min_inferences` | 最少推断数 | 防止空白 trace | 1 |
| `question_answer.constraints.enable_counterexample` | 反例对比 | 要求说明“为何不选其它方案” | true（已启用） |
| `design_questions.constraints.enable_counterexample` | 设计反例对比 | 同上 | true（已启用） |
| `question_answer.constraints.enable_arch_constraints` | 架构约束注入 | 把约束写进提示词 | true（已启用） |
| `design_questions.constraints.enable_arch_constraints` | 设计约束注入 | 同上 | true（已启用） |
| `core.architecture_constraints_path` | 架构约束清单 | 约束条目来源 | 指向 YAML |

## 🛠️ 它是如何工作的（逻辑流向）

```mermaid
flowchart TD
  A[生成答案/设计] --> B[输出结构化 trace]
  B --> C[验证 trace 结构与证据]
  C --> D[必要时记录 warn 或 reject]

  subgraph 业务规则
    B --> B1[必须包含 observations/inferences]
    B --> B2[可选反例对比与架构约束提示]
    C --> C1[trace 与 answer 一致性检查]
  end
```

## 🧩 解决的痛点与带来的改变

- **以前的乱象**：答案只有结论，无法知道依据与思路。
- **现在的秩序**：每条答案都有“可检查的推理痕迹”。

## 💡 开发者笔记

- 默认是 warn-only，不会阻断流水线；如需强约束可切到 `reject`。
- 架构约束与反例对比为 prompt 注入，不改变数据结构，适合 demo 快速迭代。
