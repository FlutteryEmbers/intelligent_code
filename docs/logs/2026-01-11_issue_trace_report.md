# 问题追踪报告: Design 样本 evidence_refs 为空导致 clean 缺失
>
> 日期: 2026-01-11

## 1. 核心业务流程分析

Design 流程由 `DesignGenerationStep` 触发，`DesignGenerator` 通过 Retriever 获取相关符号并构建 context，使用 `configs/prompts/arch_design/system.txt` + `configs/prompts/arch_design/gen_s_user.txt` 调用 LLM 生成 `answer` 与 `thought`，结果写入 `data/intermediate/design_raw.jsonl`。随后 `ValidationStep` 对 `design_raw.jsonl` 执行校验，若 `thought.evidence_refs` 为空则判定 `EVIDENCE_MISSING` 并写入 `data/intermediate/rejected/design_validation_rejected.jsonl`，导致 `data/intermediate/clean/design_clean.jsonl` 无样本生成。当前 `data/reports/design_quality.json` 显示 `passed=0` 且失败原因为 `EVIDENCE_MISSING`，与现象一致。

## 2. 潜在问题排查列表

| 可能性等级 | 潜在原因 | 涉及核心文件 |
| :--- | :--- | :--- |
| High | LLM 输出缺少 `thought.evidence_refs` 或 `thought` 整体缺失，`DesignGenerator` 未在写入前强制校验，最终全部样本在 Validation 被拒 | `src/engine/generators/arch_design/design_generator.py`, `src/utils/data/validator.py` |
| High | System Prompt 要求输出完整字段且 evidence_refs≥2，但 User Prompt 要求仅输出 answer/thought，指令冲突导致模型忽略 evidence_refs | `configs/prompts/arch_design/system.txt`, `configs/prompts/arch_design/gen_s_user.txt` |
| Medium | context 过长或证据提示位置靠前导致模型忽略 `service_evidence`，未按“复制元数据”执行 | `src/engine/generators/arch_design/design_generator.py`, `configs/prompts/arch_design/gen_s_user.txt` |
| Medium | 负向规则注入未强调 evidence_refs 必须填写，负样本更易产出空引用 | `configs/prompts/qa_rule/negative_rules.yaml`, `src/engine/generators/arch_design/design_generator.py` |
| Low | 质量门禁默认对 evidence 缺失直接 fail，因此 clean 文件为空是“预期表现”而非校验未生效 | `src/utils/data/validator.py`, `src/pipeline/steps/validation.py` |

## 3. 详细分析与修复建议

### 3.1 LLM 未输出 evidence_refs

- **逻辑缺陷**: `DesignGenerator` 仅透传 LLM 输出，`thought` 缺失时会创建空结构，导致 evidence_refs=0；校验阶段直接 fail。
- **影响文件**:
  - `src/engine/generators/arch_design/design_generator.py`
  - `src/utils/data/validator.py`
- **修复方案**:
  - 强化 `gen_s_user.txt`，显式写明 “evidence_refs 必须至少包含 1~2 条，且从输入 JSON 块复制”，并把 evidence 说明移到输出要求附近。
  - 运行时若发现 evidence_refs 为空，记录拒绝原因并触发重试或回滚到用户问题源（仅建议，不直接改代码）。

### 3.2 System/User Prompt 冲突

- **逻辑缺陷**: System Prompt 要求输出包含 `scenario/instruction/context/repo_commit` 与 evidence_refs≥2，但 User Prompt 要求只输出 `answer` 与 `thought`；指令冲突可能导致模型选择“最小输出”并忽略 evidence_refs。
- **影响文件**:
  - `configs/prompts/arch_design/system.txt`
  - `configs/prompts/arch_design/gen_s_user.txt`
- **修复方案**:
  - 对齐两份 Prompt 的输出结构，保留一致的字段要求；若选择最小结构，System Prompt 也应移除完整字段要求并强调 evidence_refs 必填。

### 3.3 证据提示被上下文稀释

- **逻辑缺陷**: evidence JSON 位于中段，且 context 体量大；模型可能忽略该段落，导致引用缺失。
- **影响文件**:
  - `configs/prompts/arch_design/gen_s_user.txt`
  - `src/engine/generators/arch_design/design_generator.py`
- **修复方案**:
  - 将 evidence JSON 放到输出要求之前或紧邻模板示例，并添加“若不填写将被拒绝”的提示。

---
