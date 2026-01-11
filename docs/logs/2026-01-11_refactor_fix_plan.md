# 修复计划（不含 LLM-as-a-Judge）
>
> 关联审计: `docs/logs/2026-01-11_design_audit_report.md`
> 日期: 2026-01-11
> 说明: 明确忽略 LLM-as-a-Judge（未计划功能），以下仅针对其他偏差与风险给出修复计划。

## 1. 修复目标与范围

- **目标**：修正文档与代码不一致、提升检索/配置可靠性、减少日志泄漏与噪声。
- **范围**：`docs/**`、`tools/**`、`src/engine/**`、`src/pipeline/**`、`configs/**`。
- **明确不做**：LLM-as-a-Judge 相关能力与配置（见 `docs/patchs/feature_quality_gate_design.md:225`、`docs/patchs/feature_raw_quality_gate_design.md:192`，仅作为不执行条目）。

## 2. 优先级修复计划

### P0（High）文档与工具路径对齐

- **问题**：文档要求 `data_validator/`，实际工具在 `tools/`。
- **证据**：`docs/features/05_observability/report_visualization.md:9`、`docs/guides/data_validator_guide.md:3`、`tools/README.md:8`。
- **修复动作**：
  1. 统一命名与路径（建议方案：将文档与 README 全量指向 `tools/render_reports.py`）。
  2. 替换所有 `data_validator/*` 引用为 `tools/*`。
  3. 更新运行命令与输出目录说明（例如 `tools/results/`）。
- **验收标准**：文档中的命令可直接执行，且路径不存在的引用为 0。

### P0（High）旧引擎路径与 Prompt 路径清理

- **问题**：`docs/**` 仍引用旧引擎文件与旧 prompt 目录。
- **证据**：`docs/features/02_generation/qa_generation.md:11`、`docs/raw/rubric_filled.md:9`。
- **修复动作**：
  1. 全局替换旧路径：`src/engine/auto_*` → `src/engine/generators/**`。
  2. Prompt 目录更新：`configs/prompts/question_answer/*` → `configs/prompts/qa_rule/*`。
  3. 更新 `docs/raw/rubric_filled.md` 证据引用以反映真实路径。
- **验收标准**：`rg "src/engine/auto_" docs` 无结果；所有 prompt 路径可找到真实文件。

### P1（Med）RAG keyword fallback 的 profile 注入修复

- **问题**：`Retriever` 使用不存在的 `profile_data` 属性，导致 fallback 无 profile。
- **证据**：`src/engine/rag/retriever.py:83`-`88`；`src/utils/generation/language_profile.py:20`-`22`。
- **修复动作**：
  1. 将 `language_profile=self.profile.profile_data` 修正为 `language_profile=self.profile.data`。
  2. 若需稳定字段名，新增 `LanguageProfile.profile_data` 只读属性作为别名。
  3. 增加单测覆盖 keyword fallback 分支。
- **验收标准**：keyword fallback 可收到 profile 字段并影响结果。

### P1（Med）Config reload 可靠性

- **问题**：`DesignGenerationStep` 未 `reload(self.args.config)`，可能使用默认配置。
- **证据**：`src/pipeline/steps/design_generation.py:50`、`src/pipeline/steps/design_generation.py:80`。
- **修复动作**：
  1. 与 `method_understanding` / `question_answer` 对齐：显式 `Config().reload(self.args.config)`。
  2. 增加“单步运行”路径的配置一致性测试。
- **验收标准**：单独运行 Step 时配置与 CLI 指定一致。

### P1（Med）日志脱敏与降噪

- **问题**：`AnswerGenerator` 在 INFO 级别输出 DEBUG 内容（含 evidence refs）。
- **证据**：`src/engine/generators/qa_rule/answer_generator.py:158`-`169`、`src/engine/generators/qa_rule/answer_generator.py:223`。
- **修复动作**：
  1. 将 DEBUG 信息下调到 DEBUG 级别。
  2. 引入最小化脱敏（例如仅保留 `symbol_id` 的末尾或 hash）。
- **验收标准**：INFO 日志中不包含文件路径/源码片段。

### P2（Low）Prompt 硬编码残留

- **问题**：`LLMClient` 内置测试 prompt 与“零硬编码”目标冲突。
- **证据**：`src/engine/core/llm_client.py:313`-`331`。
- **修复动作**：
  1. 将测试 prompt 移动到 `configs/prompts/test/connection_test_system.txt` 或专用测试文件。
  2. 测试代码读取模板而非内嵌文本。
- **验收标准**：`src/engine/core/llm_client.py` 无硬编码 prompt 文本。

### P2（Low）Seed Data 来源统一

- **问题**：`design_questions.yaml` / `user_questions.yaml` 的路径与文档约定不一致。
- **证据**：`docs/patchs/refactor_engine.md:118`-`119`；`src/engine/generators/arch_design/design_generator.py:66`-`67`；`src/engine/generators/qa_rule/question_generator.py:32`-`33`。
- **修复动作**：
  1. 统一到 `configs/user_inputs/`，并调整默认读取路径。
  2. 在 `configs/launch.yaml` 中显式配置路径，避免隐式默认。
- **验收标准**：路径一致且仅存在一份有效 seed 配置。

## 3. 风险与依赖

- **依赖**：文档修复需要全局替换与人工复核，避免误替换旧路径。
- **风险**：配置路径调整可能影响既有脚本调用方式，需同步更新 `README.md` 与示例命令。
- **回滚策略**：所有改动仅触及文档与配置映射，回滚为恢复原文档引用与默认路径。

