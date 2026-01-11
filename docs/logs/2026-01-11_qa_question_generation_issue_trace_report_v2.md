# 问题追踪报告: QA 问题生成 evidence_refs 字段缺失
>
> 日期: 2026-01-11

## 1. 核心业务流程分析

- MethodProfile 由 `method_profile/user.txt` 提示词生成，要求输出 `evidence_refs` 且包含 `source_hash`（`configs/prompts/method_profile/user.txt`）。
- QA 问题生成由 `QuestionGenerator` 驱动：
  - 构造 `default_ref` 与 `available_evidence_refs` 并注入到用户提示词（`src/engine/generators/qa_rule/question_generator.py:288-325`）。
  - 解析 LLM 输出后调用 `evidence_refs_missing_fields` 校验字段完整性（`src/engine/generators/qa_rule/question_generator.py:29-40`）。
  - 当 `quality.gate_mode=gate` 时，字段缺失直接写入 warning 并跳过（`src/engine/generators/qa_rule/question_generator.py:342-356`；`configs/launch.yaml:228-233`）。
- 当前 warnings 文件中所有样本错误为 `evidence_refs missing required fields`，且 raw evidence_refs 只包含 `symbol_id/file_path/start_line/end_line`，缺 `source_hash`（`data/intermediate/warnings/question_generation_warnings.jsonl`）。

## 2. 潜在问题排查列表

| 可能性等级 | 潜在原因 | 涉及核心文件 |
| :--- | :--- | :--- |
| High | LLM 输出未包含 `source_hash`（模板未生效或模型忽略），导致 evidence_refs 字段缺失 | `configs/prompts/qa_rule/gen_q_user.txt`, `configs/prompts/qa_rule/coverage_gen_q_user.txt`, `src/engine/generators/qa_rule/question_generator.py` |
| High | `gate_mode=gate` 禁止修复缺字段，所有缺字段样本直接记录 warning 并丢弃 | `configs/launch.yaml`, `src/engine/generators/qa_rule/question_generator.py` |
| High | Prompt 过长导致 evidence block 被截断或稀释，模型只复制前四个字段 | `configs/prompts/qa_rule/*`, `src/engine/generators/qa_rule/question_generator.py` |
| Medium | MethodProfile 输出的 evidence_refs 字段不完整（source_hash 空/缺失）导致可用证据不完整 | `configs/prompts/method_profile/user.txt`, `src/engine/generators/method_profile/understander.py` |
| Medium | Prompt 模板路径解析异常，实际加载的模板不包含 evidence_refs 模板块 | `configs/launch.yaml`, `src/engine/core/base_generator.py` |
| Low | LLM 输出结构异常（如 evidence_refs 嵌套或字段被截断），被统一归为缺字段 | `src/utils/io/file_ops.py`, `src/engine/core/base_generator.py` |

## 3. 详细分析与修复建议

### 3.1 LLM 输出未包含 source_hash（模板未生效或模型忽略）

- **逻辑缺陷**: warning 样本 raw evidence_refs 缺 `source_hash`，而校验要求五字段齐全（`src/engine/generators/qa_rule/question_generator.py:26-40`）。这会在 gate 模式下导致全部样本被丢弃。
- **影响文件**:
  - `configs/prompts/qa_rule/gen_q_user.txt`
  - `configs/prompts/qa_rule/coverage_gen_q_user.txt`
  - `src/engine/generators/qa_rule/question_generator.py`
- **修复方案**:
  - 确认实际使用的模板包含“可用证据引用”区块与 `source_hash`（检查 `question_answer.prompts.*` 是否指向正确文件）。
  - 将 `evidence_refs` 要求放到输出格式前置，并强调字段完整性。
- **建议增设日志**:
  - 输出每次生成所用 `template_name`、`question_answer.prompts.*` 的解析结果。
  - 在 warnings 中增加 `missing_fields` 列表（例如 `['source_hash']`）。

### 3.2 gate 模式下禁止修复导致全量警告

- **逻辑缺陷**: `gate_mode=gate` 时，任何 evidence_refs 字段缺失都会写 warning 并跳过，导致 QA clean 为空（`configs/launch.yaml:228-233`；`src/engine/generators/qa_rule/question_generator.py:342-356`）。
- **影响文件**:
  - `configs/launch.yaml`
  - `src/engine/generators/qa_rule/question_generator.py`
- **修复方案**:
  - 继续保持 gate 模式，但必须保证 evidence_refs 输出完整；否则 QA 将持续为 0。
  - 如需快速恢复数据，使用 report 模式并标记 `evidence_autofill`（业务决策）。
- **建议增设日志**:
  - 在 warning 汇总报告中输出 `gate_mode`、`invalid_samples` 与 `missing_fields` 分布。

### 3.3 Prompt 过长导致证据块被忽略

- **逻辑缺陷**: MethodProfile + 源码 + 约束可能过长，LLM 在输出时仅复制部分证据字段，遗漏 `source_hash`。
- **影响文件**:
  - `configs/prompts/qa_rule/gen_q_user.txt`
  - `configs/prompts/qa_rule/coverage_gen_q_user.txt`
- **修复方案**:
  - 精简输入，保留 `available_evidence_refs` 独立区块且靠近输出格式。
- **建议增设日志**:
  - 记录 prompt 字符长度与 LLM 输出长度；当超阈值时告警。

### 3.4 MethodProfile evidence_refs 不完整

- **逻辑缺陷**: 若 MethodProfile 的 evidence_refs 缺字段，会污染后续 evidence 提示块。
- **影响文件**:
  - `configs/prompts/method_profile/user.txt`
  - `src/engine/generators/method_profile/understander.py`
- **修复方案**:
  - 在 MethodProfile 生成后统计 evidence_refs 字段完整性，异常时写入专用 warning。
- **建议增设日志**:
  - 输出 method_profile evidence_refs 的字段完整性统计（missing source_hash 计数）。

### 3.5 模板路径解析异常

- **逻辑缺陷**: 如果 `question_answer.prompts.coverage_generation` / `question_generation` 指向不存在或错误路径，模板解析会回退或报错，导致 evidence_refs 模板块缺失（`src/engine/core/base_generator.py:86-116`）。
- **影响文件**:
  - `configs/launch.yaml`
  - `src/engine/core/base_generator.py`
- **修复方案**:
  - 校验模板路径存在性，启动时打印实际加载模板名。
- **建议增设日志**:
  - 启动时打印 `template_name` 与模板文件路径。

---
请现在开始执行分析，并确认你已知晓“禁止修改源码”的指令。
