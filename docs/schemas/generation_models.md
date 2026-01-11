# Generation Models

这些模型作为生成过程中的中间状态，用于承载 LLM 对代码的理解、生成的问题等。

## class `MethodProfile`
> 定义位置: `src/schemas/generation.py`

方法级理解的中间表示（语义文档），支撑 Auto QA 生成。

| 字段 | 说明 |
|---|---|
| `symbol_id` | 关联的 `CodeSymbol` ID。 |
| `summary` | 方法摘要（用于 Embedding 检索）。 |
| `business_rules` | 抽取出的业务规则列表。 |
| `inputs` / `outputs` | 结构化的输入输出语义描述。 |
| `dependencies` | 方法的依赖项描述。 |
| `evidence_refs` | 支撑理解的证据引用。 |

## class `QuestionSample`
> 定义位置: `src/schemas/generation.py`

在 Auto Question Generator 与 Answer Generator 之间传递的对象。

| 字段 | 说明 |
|---|---|
| `question` | 问题文本。 |
| `question_type` | 问题分类标签 (e.g., `usage`, `logic`)。 |
| `difficulty` | 难度 (`easy`, `medium`, `hard`)。 |
| `evidence_refs` | 与问题生成直接相关的证据。 |
| `evidence_autofill` | 是否由系统自动补齐 evidence_refs（report 模式可出现）。 |

## dict `DesignQuestion`
> 定义位置: `src/engine/generators/arch_design/question_generator.py` (非 Pydantic Model)

用于架构设计生成模块的输入对象。

| 字段 | 说明 |
|---|---|
| `id` | 问题 ID (e.g., `DQ-AUTO-001`)。 |
| `goal` | 设计目标。 |
| `constraints` | 架构约束列表 (e.g., "Must communicate via PubSub")。 |
| `acceptance_criteria` | 验收标准。 |
| `non_goals` | 非目标列表。 |
| `evidence_refs` | 相关的代码证据列表。 |
| `evidence_autofill` | 是否由系统自动补齐 evidence_refs（report 模式可出现）。 |
| `question_type` | 默认 `architecture`。 |
