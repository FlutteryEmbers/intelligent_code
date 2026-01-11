# 设计一致性审计报告
> 问题总结: 审计训练集生成流水线是否符合 rubric 质量要求，并识别可能绕过下游校验的实现路径
> 审计对象: `src/engine/` + `src/pipeline/` + `src/utils/`
> 审计基准: `docs/raw/rubric_template.md`
> 日期: 2026-01-11

## 1. 总体合规度摘要

- **完全符合**: 约 50%
- **存在偏差**: 7 个模块
- **严重缺失**: 4 个功能点

## 2. 差异矩阵 (Discrepancy Matrix)

| 模块/功能 | 设计要求 | 代码现状 | 差异严重度 (High/Med/Low) |
| :--- | :--- | :--- | :--- |
| Gate 模式合并策略 | gate 模式仅允许 clean 数据进入下游 | Design clean 缺失时仍合并 raw | High |
| 证据锚定一致性 | evidence_refs 必须由模型显式输出 | QA Answer 自动补 evidence_refs | High |
| 出题证据完整性 | 出题 evidence_refs 应反映 LLM 输出 | QA/Design 出题阶段强制覆盖或补齐 evidence_refs | Med |
| 场景注入 | 设计问题需按比例注入模糊/指代问题 | Design 出题固定 `scenario_constraints="无"` | Med |
| LLM-as-a-Judge | 需要自动评分/判别接口 | 未发现 judge 相关步骤 | High |
| Trace Anchor | 推理链需包含逐步证据锚点 | 仅校验 EvidenceRef 元数据 | Med |
| 反馈闭环 | Bad Case 应触发回归与再生成 | 仅记录报表，无自动再生成 | Med |

## 3. 详细审计发现

### 3.1 接口一致性

- **设计描述**: Pipeline 步骤应提供稳定的质量门禁接口，gate 模式不允许未校验样本进入。
- **代码实现**: QA clean 缺失会抛错；Design clean 缺失仅告警且继续合并 raw。
- **证据**: `src/pipeline/steps/merge.py:94`-`116`。
- **主要问题**: gate 模式下 Design 侧存在“原始样本直通”路径，接口语义与 gate 目标不一致。
- **建议行动**: gate 模式下 Design 与 QA 统一为“缺失 clean 即阻断或 0 样本”。

### 3.2 数据模型一致性

- **设计描述**: 样本的 evidence_refs 应来源于模型显式输出，体现可审计的证据链。
- **代码实现**:
  - QA 出题阶段强制覆盖 evidence_refs 为 default_ref。`src/engine/generators/qa_rule/question_generator.py:212`-`258`。
  - Design 出题阶段缺失 evidence_refs 时直接补 `evidence_pool[0]`。`src/engine/generators/arch_design/question_generator.py:150`-`155`。
  - QA Answer 在仅 1 个符号时自动补 evidence_refs。`src/engine/generators/qa_rule/answer_generator.py:357`-`373`。
- **主要问题**: evidence_refs 被系统层强行补齐，掩盖模型未产出证据的事实，弱化了“证据锚定”的数据模型语义。
- **建议行动**: 对自动补齐样本打标并在 gate 模式 reject，或强制 LLM 输出证据后才通过。

### 3.3 业务逻辑完整性（工作流追溯 + 作弊风险）

- **设计描述**: 训练集生成需严格通过 Validation → Coverage → Merge → Dedup → Safety → Split。
- **代码实现**: 流程顺序存在，但 Design 侧 gate 允许 raw 混入（详见 3.1）。
- **证据**: `src/pipeline/orchestrator.py:166`-`180`。
- **主要问题**: 形成“未校验样本进入下游”的路径，属于绕过检查的高风险点。
- **建议行动**: gate 模式下严格阻断 raw 合并，并在报表中单独统计 bypass。

### 3.4 命名与规范

- **设计描述**: rubric 要求 trace 需逐步锚定 (File:L#Line)。
- **代码实现**: Validator 仅校验 EvidenceRef 元数据，不要求 step-level 锚点。`src/utils/data/validator.py:118`-`176`。
- **主要问题**: 未实现“推理链条逐步锚定”的规范要求。
- **建议行动**: Prompt 中要求每条 observation/inference 带 File:L#Line 或在 Validation 增加结构化锚点校验。

### 3.5 rubric 覆盖项对照 (摘要)

- **Distribution Control**: 覆盖桶/意图/模块跨度推断与采样存在（`src/utils/data/coverage.py:56`-`114`, `src/pipeline/steps/coverage_sampler.py:220`-`299`）。Design 场景注入缺失（`src/engine/generators/arch_design/question_generator.py:120`-`122`）。
- **Grounding Integrity**: evidence_refs 校验存在，但自动补齐可绕过（见 3.2）。
- **Reasoning Trace**: 结构化 thought 存在，逐步锚点缺失（见 3.4）。
- **Robustness & Negative Samples**: 负采样机制存在（`src/utils/data/sampling.py:93`-`123`），规则通过 prompt 注入。
- **Data Engineering**: 长度校验与安全扫描存在（`src/utils/data/validator.py:192`-`219`, `src/pipeline/steps/secrets_scan.py:28`-`116`）；语义去重可选但默认关闭（`src/pipeline/steps/deduplication.py:44`-`60`）。
- **Verification & Feedback**: 报表输出存在（coverage/question_type），未发现 judge 或自动回归重生成步骤。

---
**请确认你已理解“只读模式”并开始执行审计。**
