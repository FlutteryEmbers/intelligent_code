# 问题追踪报告: QA 问题生成 evidence_refs.source_hash 缺失
>
> 日期: 2026-01-11

## 1. 核心业务流程分析

QA 问题生成流程为 MethodProfile → QuestionGenerator → LLM 输出 questions → Pydantic 校验 QuestionSample。当前告警来自 `QuestionGenerator` 在构造 `QuestionSample` 时发现 `evidence_refs` 中缺少 `source_hash`，导致样本被丢弃并记录 warning。

涉及路径：
- `src/engine/generators/qa_rule/question_generator.py`（QuestionSample 校验与告警）
- `configs/prompts/qa_rule/gen_q_user.txt` / `configs/prompts/qa_rule/coverage_gen_q_user.txt`（evidence_refs 输出要求）
- `configs/prompts/method_profile/user.txt`（MethodProfile evidence_refs 提示）

## 2. 潜在问题排查列表

| 可能性等级 | 潜在原因 | 涉及核心文件 |
| :--- | :--- | :--- |
| High | LLM 未按模板输出完整 evidence_refs 字段，省略了 source_hash | `configs/prompts/qa_rule/gen_q_user.txt`, `configs/prompts/qa_rule/coverage_gen_q_user.txt` |
| High | QuestionGenerator 仅在 evidence_refs 为空时补齐 default_ref，对“字段缺失”的 evidence_refs 未做纠正 | `src/engine/generators/qa_rule/question_generator.py` |
| Medium | MethodProfile JSON 过长或上下文噪声导致 LLM 忽略 evidence_refs 结构 | `src/engine/generators/qa_rule/question_generator.py` |
| Low | MethodProfile 生成阶段 evidence_refs 不稳定，导致 LLM 未找到可复制字段 | `configs/prompts/method_profile/user.txt`, `src/engine/generators/method_profile/understander.py` |

## 3. 详细分析与修复建议

### 3.1 LLM 输出 evidence_refs 缺字段

- **逻辑缺陷**: LLM 输出的 evidence_refs 未包含 `source_hash`，触发 Pydantic 校验失败。
- **影响文件**:
  - `configs/prompts/qa_rule/gen_q_user.txt`
  - `configs/prompts/qa_rule/coverage_gen_q_user.txt`
- **修复方案**:
  - 强化提示：在输出要求中强调 evidence_refs 必须逐字段完整复制（包含 `source_hash`），并在示例中强调 `source_hash` 不可省略。

### 3.2 缺字段不触发自动纠正

- **逻辑缺陷**: 当前仅在 evidence_refs 为空时补齐 default_ref，字段缺失不会修复，直接导致样本丢弃。
- **影响文件**:
  - `src/engine/generators/qa_rule/question_generator.py`
- **修复方案**:
  - 将“字段缺失”视为 evidence_refs 缺失：在 report 模式下补齐 default_ref；在 gate 模式下保留为失败样本。

### 3.3 Prompt 输入过长导致结构信息被忽略

- **逻辑缺陷**: MethodProfile JSON + 源码上下文过长，LLM 可能忽略 evidence_refs 字段。
- **影响文件**:
  - `src/engine/generators/qa_rule/question_generator.py`
- **修复方案**:
  - 在 prompt 中增加“可复制 evidence_refs 模板块”，减少模型搜索负担；或缩短输入正文（保留 evidence_refs 与必要摘要）。

---
请现在开始执行分析，并确认你已知晓“禁止修改源码”的指令。
