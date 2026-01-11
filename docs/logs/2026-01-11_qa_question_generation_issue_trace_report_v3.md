# 问题追踪报告: QA 出题 evidence_refs 缺 source_hash
>
> 日期: 2026-01-11

## 1. 核心业务流程分析

- MethodProfile 生成阶段已包含完整 evidence_refs（含 `source_hash`），样例与统计均满足：`data/intermediate/method_profiles.jsonl` 中 **0 行缺失 source_hash**。
- QuestionGenerator 将 MethodProfile 与源码注入 prompt，LLM 输出 `questions[].evidence_refs` 后做字段完整性校验；`gate_mode=gate` 时直接写 warning 并丢弃样本。
- 当前 warnings 文件统计显示 **189/189 条** warning 均缺 `source_hash`，其余字段 (`symbol_id/file_path/start_line/end_line`) 均存在，说明缺失集中在单字段。

## 2. 潜在问题排查列表

| 可能性等级 | 潜在原因 | 涉及核心文件 |
| :--- | :--- | :--- |
| High | LLM 未按模板复制 `source_hash`，导致 evidence_refs 字段不完整（即使上游 MethodProfile 完整） | `configs/prompts/qa_rule/gen_q_user.txt`, `configs/prompts/qa_rule/coverage_gen_q_user.txt`, `src/engine/generators/qa_rule/question_generator.py` |
| High | `gate_mode=gate` 禁止修复缺字段，所有缺 `source_hash` 的样本被直接记录 warning | `configs/launch.yaml`, `src/engine/generators/qa_rule/question_generator.py` |
| Medium | 当前 warnings 可能来自旧版本 prompt（未包含 evidence block），未反映最新提示 | `data/intermediate/warnings/question_generation_warnings.jsonl`, `configs/prompts/qa_rule/*` |
| Medium | Prompt 过长/证据块位置靠后，模型只复制了 4 字段，忽略 `source_hash` | `configs/prompts/qa_rule/*` |
| Low | 模板解析未命中（实际使用了缺少 evidence block 的模板） | `configs/launch.yaml`, `src/engine/core/base_generator.py` |

## 3. 详细分析与修复建议

### 3.1 LLM 输出缺 `source_hash`（上游证据完整，说明问题集中在生成阶段）

- **逻辑缺陷**: MethodProfile 中 evidence_refs 已包含 `source_hash`，但 warnings 显示 LLM 输出的 evidence_refs 缺该字段，说明模型未复制完整字段。
- **影响文件**:
  - `configs/prompts/qa_rule/gen_q_user.txt`
  - `configs/prompts/qa_rule/coverage_gen_q_user.txt`
  - `src/engine/generators/qa_rule/question_generator.py`
- **修复方案**:
  - 确认运行时使用的模板确实包含“可用证据引用”块并强调 `source_hash`。
  - 将 evidence_refs 模板块放置在输出格式前置位置，并将“缺字段即无效”明示为硬约束。
- **建议增设日志**:
  - 输出实际加载的 `template_name` 与模板路径。
  - 对每次生成记录 `available_evidence_refs` 的条数与首条（包含 source_hash）。
  - 对每个 warning 增加 `missing_fields` 数组（如 `["source_hash"]`）。

### 3.2 gate 模式严格校验导致全量丢弃

- **逻辑缺陷**: `gate_mode=gate` 使缺字段样本直接落入 warnings；当 LLM 普遍漏 `source_hash` 时，QA clean 将为 0。
- **影响文件**:
  - `configs/launch.yaml`
  - `src/engine/generators/qa_rule/question_generator.py`
- **修复方案**:
  - 保持 gate 模式，但必须保证 LLM 输出完整字段；否则 QA 产出会持续为 0。
- **建议增设日志**:
  - 在警告汇总报告中记录 `gate_mode` 与 `missing_fields` 统计。

### 3.3 warnings 可能来自旧版本 prompt

- **逻辑缺陷**: warnings 文件的样本可能对应旧 prompt，无法验证当前 prompt 是否有效。
- **影响文件**:
  - `data/intermediate/warnings/question_generation_warnings.jsonl`
  - `configs/prompts/qa_rule/*`
- **修复方案**:
  - 重新运行一次 QA 出题流程，用最新 prompt 生成新的 warnings，再对比变化。
- **建议增设日志**:
  - 在 warnings JSONL 中记录 prompt 版本或模板名。

---
请现在开始执行分析，并确认你已知晓“禁止修改源码”的指令。
