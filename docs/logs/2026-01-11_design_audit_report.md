# 设计一致性审计报告
>
> 审计对象: `src/engine/` + `src/pipeline/` + 可观测性工具（与报表可视化相关）
> 审计基准: `docs/patchs/refactor_engine.md` + `docs/features/**` + `docs/guides/**` + `docs/raw/rubric_filled.md`
> 日期: 2026-01-11

## 1. 总体合规度摘要

- **重构方向符合**：`src/engine/core/base_generator.py` 已实现模板 + language profile 的组合（Prompt 零硬编码方向），`src/engine/rag/retriever.py` 已抽出检索模块。
- **文档一致性不足**：大量 `docs/**` 仍引用旧的引擎路径、Prompt 路径与 `data_validator/` 目录，导致“按文档执行”会失败或误导。
- **关键能力缺口**：按 `docs/patchs/feature_quality_gate_design.md` / `docs/patchs/feature_raw_quality_gate_design.md` 描述的 LLM-as-a-Judge 质量门禁（judge 评分与缓存）未在代码中落地。

## 2. 差异矩阵 (Discrepancy Matrix)

| 模块/功能 | 设计要求 | 代码现状 | 差异严重度 (High/Med/Low) |
| :--- | :--- | :--- | :--- |
| 可视化模块位置 | 文档要求存在 `data_validator/`（见 `docs/guides/data_validator_guide.md:3`、`docs/features/05_observability/report_visualization.md:9`） | 仓库无 `data_validator/` 目录；实际脚本在 `tools/render_reports.py` | High |
| 引擎模块命名/引用 | 多处文档仍引用 `src/engine/auto_question_generator.py` 等（见 `docs/raw/rubric_filled.md:9`、`docs/features/02_generation/qa_generation.md:11`） | 实际生成器位于 `src/engine/generators/**`（如 `src/engine/generators/qa_rule/question_generator.py`） | High |
| BaseGenerator 职责收敛 | 设计要求 Base 层含 `_inject_negative_rules` / `_clean_and_parse_json` / `_retrieve_context`（见 `docs/patchs/refactor_engine.md:168`-`188`） | `src/engine/core/base_generator.py` 仅实现模板加载与 `generate_with_retry`，负向规则与检索委托分散在子类 | Med |
| Seed Data 位置约定 | `design_questions.yaml` / `user_questions.yaml` 应保留在 `configs/user_inputs/`（见 `docs/patchs/refactor_engine.md:118`-`119`） | 代码默认读 `configs/design_questions.yaml`（见 `src/engine/generators/arch_design/design_generator.py:66`-`67`）与 `configs/user_questions.yaml`（见 `src/engine/generators/qa_rule/question_generator.py:32`-`33`） | Med |
| Keyword 检索的 profile 注入 | 关键字检索应利用 language profile（增强语义与权重） | `src/engine/rag/retriever.py:87`-`88` 使用不存在的 `profile_data` 属性，导致 `keyword_search(..., language_profile=None)` | Med |
| 质量门禁（LLM-as-a-Judge） | 文档要求 judge 结果写入 `quality.scores/judge` 并缓存（见 `docs/patchs/feature_quality_gate_design.md:228`-`229`） | 代码侧未找到 judge/评分模块（仅文档存在） | High |

## 3. 详细审计发现

### 3.1 可观测性：`data_validator/` 与实际实现不一致（High）

- **设计描述**：文档将报表可视化与一致性校验定位在 `data_validator/`（`docs/features/05_observability/report_visualization.md:9`-`17`、`docs/guides/data_validator_guide.md:3`、`docs/guides/data_validator_guide.md:16`）。
- **代码实现**：仓库无 `data_validator/` 目录；仅存在 `tools/render_reports.py` 与 `tools/results/`。
- **影响**：
  - 直接按文档运行 `python data_validator/render_reports.py` 会失败（目录不存在）。
  - `tools/README.md:8`-`12` 同样引用了不存在的 `data_validator/requirements.txt` 与路径，进一步放大误导。
- **建议行动**：统一路径与命令（要么恢复 `data_validator/`，要么系统性更新所有文档与 README 指向 `tools/`）。

### 3.2 文档引用未随重构同步（High）

- **设计描述**：重构后应同步更新文档引用（`docs/patchs/refactor_engine.md:192`-`200`）。
- **代码现状**：`docs/raw/rubric_filled.md` 仍引用 `src/engine/auto_question_generator.py` / `src/engine/answer_generator.py` 等旧路径（如 `docs/raw/rubric_filled.md:9`、`docs/raw/rubric_filled.md:22`、`docs/raw/rubric_filled.md:38`）。
- **影响**：审计证据链与“代码事实”无法对应，导致后续审计/回归排查成本显著上升。
- **建议行动**：对 `docs/**` 做一次全局路径引用修复（至少覆盖 `src/engine/*` → `src/engine/generators/**`、`configs/prompts/question_answer/*` → `configs/prompts/qa_rule/*`、`data_validator/*` → 实际工具路径）。

### 3.3 BaseGenerator 未按设计收敛关键能力（Med）

- **设计描述**：Base 层应提供负向规则注入、统一 JSON 清洗解析、检索委托接口（`docs/patchs/refactor_engine.md:168`-`188`）。
- **代码实现**：
  - `src/engine/core/base_generator.py:38`-`130` 实现模板加载与 prompt 组装。
  - `src/engine/core/base_generator.py:131`-`169` 实现 `generate_with_retry` + JSON 清洗/解析，但未提供 `_clean_and_parse_json` 独立入口，也未包含 `_inject_negative_rules` / `_retrieve_context`。
- **影响**：跨场景一致性与可维护性下降（规则/检索/清洗分散在多个生成器中，重构目标“职责分层”被部分削弱）。
- **建议行动**：将 `_inject_negative_rules` 等通用逻辑上收至 Base（或明确由专用组件负责，并在文档中更新职责边界）。

### 3.4 RAG：keyword_search 的 profile 参数实际未生效（Med）

- **设计描述**：RAG 下沉后应可复用，并利用 profile 做关键词权重/层级推断增强（`docs/patchs/refactor_engine.md:19`-`20`、`docs/patchs/refactor_engine.md:183`-`188`）。
- **代码实现**：`src/engine/rag/retriever.py:83`-`88` 与 `src/engine/rag/retriever.py:141`-`146` 试图传入 `language_profile=self.profile.profile_data ...`，但 `LanguageProfile` 实际字段为 `data`（见 `src/utils/generation/language_profile.py:20`-`22`）。
- **影响**：keyword fallback 的行为退化为“无 profile”模式，可能直接拉低检索质量与层级平衡准确性。
- **建议行动**：修正为传入 `self.profile.data`（或让 `LanguageProfile` 提供稳定属性名），并补充单测覆盖该分支。

### 3.5 Pipeline：Config 单例 + 未 reload 的路径（Med）

- **现象**：`Config` 是单例（`src/utils/core/config.py:11`-`21`），`design_generation` 步骤未显式 `reload(self.args.config)`，而是直接 `Config()`（`src/pipeline/steps/design_generation.py:50`、`src/pipeline/steps/design_generation.py:80`）。
- **风险**：在“跳过前序步骤”或“单独运行某一步”的情况下，可能使用默认 `configs/launch.yaml` 而非用户传入配置，产生不可复现结果。

### 3.6 Prompt 硬编码残留（Low，但建议清理）

- **现象**：`src/engine/core/llm_client.py` 内仍包含硬编码测试 prompt（`src/engine/core/llm_client.py:313`-`331`），与“Prompt 零硬编码”的目标存在理念冲突（即便仅用于 `__main__` 自测）。
- **风险**：后续被误复制到生产路径、或被当作默认 prompt 使用的概率上升。

### 3.7 日志泄漏与噪声风险（Med）

- **现象**：`AnswerGenerator` 在 INFO 级别输出大量 DEBUG 信息与 evidence_refs（`src/engine/generators/qa_rule/answer_generator.py:158`-`169`、`src/engine/generators/qa_rule/answer_generator.py:223`、`src/engine/generators/qa_rule/answer_generator.py:226`）。
- **风险**：在真实仓库上可能泄漏文件路径/片段信息到日志，并显著增加日志量（影响运行成本与排障效率）。

## 4. 建议的优先级行动清单

1. **High**：统一 `data_validator/` vs `tools/` 的真实位置与文档引用（`docs/**` + `tools/README.md`）。
2. **High**：补齐或明确放弃 LLM-as-a-Judge 质量门禁（对应 `docs/patchs/feature_quality_gate_design.md`）。
3. **Med**：修复 `Retriever` keyword fallback 的 profile 传参（`src/engine/rag/retriever.py:87`-`88`）。
4. **Med**：降低 INFO 级别的 DEBUG 日志并做脱敏策略（`src/engine/generators/qa_rule/answer_generator.py`）。
5. **Med**：梳理并固化 seed data 的单一来源（`configs/` vs `configs/user_inputs/`），减少双份配置带来的漂移。

