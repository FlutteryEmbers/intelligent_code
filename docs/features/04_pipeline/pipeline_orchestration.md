# 流程编排与步骤执行

## 🌟 核心概念：像“总控台”一样
> 就像调度中心按顺序发车，系统会按固定流程依次执行每一步，并记录每一步的结果。

## 📋 运作基石（必要元数据）

- **涉及领地 (Code Context)**：
  - `main.py`
  - `src/pipeline/orchestrator.py`
  - `src/pipeline/base_step.py`
  - `src/pipeline/steps/*`
  - `configs/launch.yaml`

- **执行准则 (Business Rules)**：
  - 步骤按固定顺序串行执行。
  - 每个步骤先判断是否需要跳过（skip）。
  - 即使单步失败，流程仍会继续执行后续步骤，并记录失败原因。
  - 统一写出 `pipeline_summary.json` 作为流程账本。

- **参考证据**：
  - 所有步骤都以 `data/*` 工件作为输入输出，形成可回放记录。

## ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `output.*` | 输出目录集合 | 控制 raw/intermediate/final 路径 | 保持默认 |
| `logging.*` | 日志设置 | 控制日志级别与文件 | demo 级别 INFO |
| CLI: `--skip-*` | 跳过开关 | 跳过对应步骤 | 仅在调试使用 |

## 🛠️ 它是如何工作的（逻辑流向）

```mermaid
flowchart TD
  A[CLI 启动] --> B[Orchestrator]
  B --> C[Step.run]
  C --> D{是否跳过?}
  D -- 是 --> E[记录为 skipped]
  D -- 否 --> F[执行 execute]
  F --> G[记录结果]
  G --> H[进入下一步]

  subgraph 业务规则
    D --> D1[skip 逻辑]
    F --> F1[失败不阻断]
  end
```

## 🧩 解决的痛点与带来的改变

- **以前的乱象**：步骤执行不透明，难以复盘。
- **现在的秩序**：每一步都有记录与结果，可复查、可回放。

## 💡 开发者笔记

- `pipeline_summary.json` 是流程审计入口。
- 单步失败不会自动停止，适合 demo，但正式场景可考虑 fail-fast。
