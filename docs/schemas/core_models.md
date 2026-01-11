# Core Data Models

本文档定义了系统中流转的核心数据结构，它们是系统进行解析、训练样本生成、校验与导出的基础。

## class `CodeSymbol`
> 定义位置: `src/schemas/symbols.py`

代码证据的标准化单位（类/方法/字段/文件）。训练数据中所有证据引用最终都应指向某个 `CodeSymbol`。

| 字段 | 类型 | 说明 | 契约/用途 |
|---|---|---|---|
| `symbol_id` | str | 稳定主键 | 格式 `{file_path}:{qualified_name}:{start_line}`，作为引用锚点。 |
| `symbol_type` | str | 类型 | `class`,`method`,`field`,`file`。QA候选多为 method。 |
| `name` | str | 简单名 | 用于检索、显示。 |
| `qualified_name` | str | 全限定名 | 包含包路径，用于 Split 分组 (`group_by=package`)。 |
| `file_path` | str | 相对文件路径 | 证据定位与 Split 分组 (`group_by=path`)。 |
| `start_line` | int | 起始行 | 1-based。 |
| `end_line` | int | 结束行 | 1-based。 |
| `source` | str | 源码片段 | 允许截断。用于 Prompt 上下文与哈希校验。 |
| `source_hash` | str | SHA256摘要 | `sha256(source)`，防止证据漂移，必须与 EvidenceRef 匹配。 |
| `doc` | str | 文档注释 | 可为空。用于候选评分与问题生成背景。 |
| `metadata` | dict | 扩展元数据 | 包含语言特定信息（如继承关系、装饰器）。 |
| `repo_commit` | str | 仓库版本 | 必须与样本的 commit 一致。 |

## class `EvidenceRef`
> 定义位置: `src/schemas/symbols.py`

用最小字段指向“可验证的代码证据片段”。

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol_id` | str | 引用目标 `CodeSymbol.symbol_id`。 |
| `file_path` | str | 冗余字段（方便人类阅读）。 |
| `start_line` | int | 引用起始行。 |
| `end_line` | int | 引用结束行。 |
| `source_hash` | str | **关键校验位**：必须匹配 `CodeSymbol.source_hash`。 |

## class `ReasoningTrace`
> 定义位置: `src/schemas/samples.py`

结构化表达“推理痕迹”，避免自由文本 CoT 直接进入训练输出。

*   `observations` (`list[str]`): 从代码上下文观察到的事实。
*   `inferences` (`list[str]`): 由 observations 推导出的结论。
*   `evidence_refs` (`list[EvidenceRef]`): **必须**包含的证据引用列表。
*   `assumptions` (`list[str]`): 无法直接验证的假设。

## class `TrainingSample`
> 定义位置: `src/schemas/samples.py`

Pipeline 的核心业务对象，统一表达 QA 与 Architecture Design 样本。

| 字段 | 类型 | 说明 |
|---|---|---|
| `scenario` | str | `qa_rule` 或 `arch_design`。Split 依据此字段分流。 |
| `instruction` | str | 用户指令/问题。 |
| `context` | str | 构建的 RAG 上下文（源码拼接）。 |
| `thought` | ReasoningTrace | 结构化推理过程。 |
| `answer` | str | 最终答案。 |
| `quality` | dict | 质量评估结果容器 (Coverage, Quality Gate)。详见下文 `Quality Dictionary`。 |
| `sample_id` | str | 基于内容生成的稳定 ID。 |

## Semi-structured: `Quality Dictionary`
> 定义位置: `src/utils/data/validator.py` (validate_sample_obj)

注入到 `TrainingSample.quality` 中的评估结果字典。

| 字段 | 类型 | 说明 |
|---|---|---|
| `passed` | bool | 是否通过质量门禁。 |
| `gate_version` | str | 门禁版本 (e.g., "v1")。 |
| `errors` | list[dict] | 阻断性错误 (`{code, message}`)。 |
| `warnings` | list[dict] | 非阻断性警告 (`{code, message}`)。 |
| `evidence_autofill` | bool | 是否由系统补齐 evidence_refs；gate 模式下会被拒绝。 |
| `stats` | dict | 统计信息 (chars, evidence count)。 |
| `checks` | dict | 各维度的检查状态 (pass/warn/fail)。 |

## Semi-structured: `RejectedSample Wrapper`
> 定义位置: `src/utils/data/validator.py`

保存到 `rejected/*.jsonl` 的被淘汰样本包装器。

| 字段 | 说明 |
|---|---|
| `line` | 原始文件行号。 |
| `scenario` | 场景类型。 |
| `error` | (Format error) 错误信息。 |
| `quality` | (Validation error) 上述 Quality Dictionary。 |
| `raw` | 原始样本数据。 |
