# 证据锚定与 Grounding（Grounding Integrity）

## 🌟 核心概念：像“发票”一样
> 就像每一笔报销都要有发票，系统会为每条回答贴上可追溯的证据标签，确保“说得出、查得到”。

## 📋 运作基石（必要元数据）

- **涉及领地 (Code Context)**：
  - `src/parser/java_parser.py`
  - `src/parser/python_parser.py`
  - `src/engine/answer_generator.py`
  - `src/engine/design_generator.py`
  - `src/utils/validator.py`
  - `src/utils/call_chain.py`
  - `configs/launch.yaml`
  - `configs/prompts/question_answer/auto_answer_generation.txt`
  - `configs/prompts/design/design_user_prompt.txt`

- **执行准则 (Business Rules)**：
  - 每条样本必须携带 `evidence_refs`，且 **symbol_id / file_path / source_hash / line_range** 必须与 `symbols.jsonl` 一致。
  - `repo_commit` 不一致会触发告警，便于排查版本偏差。
  - 证据来自检索到的候选方法（前 N 条），回答只能选用这些证据。
  - 上下文长度被 `max_context_chars` 限制，避免“全量粘贴”。
  - 允许通过“调用链扩展”补充相关方法（弱规则）。

- **参考证据**：
  - `data/raw/extracted/symbols.jsonl` 中的 symbol 与 `repo_commit` 是证据对齐的标准。

## ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `core.retrieval_top_k` | 证据候选数量 | 决定每次检索拿多少段代码 | 6（默认） |
| `core.max_context_chars` | 上下文上限 | 控制上下文长度，避免噪音 | 16000 |
| `question_answer.retrieval.mode` | QA 检索模式 | hybrid / vector_only / symbol_only | demo 用 symbol_only |
| `question_answer.retrieval.min_score` | 相似度阈值 | 过滤低相关证据 | 0.2 |
| `question_answer.retrieval.fallback_top_k` | 回退候选数 | 相似度过滤后回退数量 | 与 top_k 一致 |
| `question_answer.retrieval.call_chain.enabled` | 调用链扩展 | 启用弱规则的依赖召回 | true（已开启） |
| `design_questions.retrieval.mode` | Design 检索模式 | hybrid / symbol_only | hybrid |
| `design_questions.retrieval.call_chain.enabled` | 设计调用链扩展 | 设计样本的依赖召回 | true（已开启） |
| `design_questions.min_evidence_refs` | 设计最少证据数 | 设计样本证据下限 | 2 |

## 🛠️ 它是如何工作的（逻辑流向）

```mermaid
flowchart TD
  A[解析代码生成 symbols.jsonl] --> B[检索候选方法（前 N 条）]
  B --> C[按上下文上限拼接证据]
  C --> D[回答/设计输出 evidence_refs]
  D --> E[验证证据一致性]
  E --> F[通过 -> clean 分支]

  subgraph 业务规则
    B --> B1[前 N 条 + 调用链扩展]
    D --> D1[evidence_refs 必须来自候选池]
    E --> E1[file_path/source_hash/line_range 对齐]
  end
```

## 🧩 解决的痛点与带来的改变

- **以前的乱象**：回答“听起来合理”，但无法定位代码出处。
- **现在的秩序**：每条回答都有“证据编号”，还能反查到具体文件与行号。

## 💡 开发者笔记

- 证据一致性失败会直接判为不合格样本。
- 调用链扩展是弱规则，适合 demo，但不会强行改变原有证据结构。
