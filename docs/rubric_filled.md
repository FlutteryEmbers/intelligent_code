# Pipeline Rubric Review（当前代码对照）

以下为根据现有代码能力对 `docs/rubric_template.md` 的逐项填写与证据引用，并附上按重要性排序的改进清单。

---

## 1. 宏观分布控制（Distribution Control）

- 配额逻辑校验：满足。证据：`src/pipeline/steps/coverage_sampler.py` 按 targets 抽样；`src/engine/auto_question_generator.py` 与 `src/engine/auto_design_question_generator.py` 上游 bucket/intent 抽取。
- 难度判定因子-模块跨度：满足。证据：`src/pipeline/steps/coverage_tagger.py` 的 `_infer_module_span`。
- 难度判定因子-evidence_refs 数量：部分满足。证据：`design_questions.min_evidence_refs` 控制最少证据，但 `coverage_tagger._infer_bucket` 未使用 evidence_refs 计数做难度判定。
- 隐含约束/反直觉 Prompt 注入：部分满足。证据：`configs/prompts/*/coverage_*_generation.txt` + `_build_constraint_rules`（`src/engine/auto_question_generator.py`、`src/engine/auto_design_question_generator.py`）为 mid/hard 注入约束，但未明确“反直觉”模板。
- 多样性采样（question_type 均衡）：未满足。证据：prompt 列出 question_type，但未有配额或抽样控制。
- 场景化注入（模糊/指代问）：未满足。证据：无对应 prompt 规则或采样逻辑。

---

## 2. 证据锚定与 Grounding

- 元数据提取准确性：满足。证据：`src/utils/validator.py` 校验 symbol_id/file_path/source_hash/commit，支持路径归一化。
- 上下文最小化逻辑：部分满足。证据：`core.retrieval_top_k` / `core.max_context_chars`；`question_answer.retrieval` 与 `design_questions.retrieval` 的 min_score/fallback；但未剔除无关代码块。
- 依赖关系/调用链召回：未满足。证据：无调用链/依赖图检索。
- Trace 锚定强制要求：未满足。证据：trace 校验存在（`quality.trace_rules`），但 prompt 未要求 (File:L#Line)。

---

## 3. 推理链路质量（Reasoning Trace Logic）

- 多步推理结构：部分满足。证据：`ReasoningTrace` 结构化 + trace 规则校验（`src/utils/validator.py`），但未强制 Analysis/Evidence/Decision 结构。
- 反例对比：未满足。证据：prompt/生成逻辑未要求“为何不采用其他方案”。
- 关联架构约束：未满足。证据：未显式引用架构约束集。
- 逻辑自洽校验：未满足。证据：无脚本校验 trace 与 answer 一致性。

---

## 4. 健壮性与负样本（Robustness & Negative Samples）

- 拒答逻辑生成：满足。证据：`negative_ratio/types` + 规则段注入（`src/engine/answer_generator.py`、`src/engine/design_generator.py`）。
- 纠错场景生成：满足。证据：`negative_types` 包含 `wrong_premise`，规则段明确纠偏。
- 冲突处理样本：满足。证据：`negative_types` 包含 `conflict_spec`。

---

## 5. 工程质量与清洗（Data Engineering）

- 长度过滤：部分满足。证据：`src/utils/validator.py` 的 min/max 长度阈值；是否拒绝取决于 `quality.fail_on_warnings`。
- 关键词黑名单：满足。证据：`src/pipeline/steps/secrets_scan.py` 支持 blacklist + keep/drop/sanitize。
- 语义去重：部分满足。证据：`src/pipeline/steps/deduplication.py` 使用 SimHash，未引入 embedding 相似度。
- 敏感信息脱敏：满足。证据：`src/pipeline/steps/secrets_scan.py` 支持 sanitize。

---

## 6. 验证与闭环（Verification & Feedback）

- LLM-as-a-Judge 接口：未满足。证据：未实现 judge 或评分接口。
- 报表输出：满足。证据：`qa_quality.json` / `design_quality.json` / `coverage_report.json` / `qa_retrieval_report.json` / `design_retrieval_report.json`，以及 `data_validator/render_reports.py` 的分布一致性校验。
- 回归机制：未满足。证据：无针对 Bad Case 的重生成/定向微调逻辑。

---

## 改进清单（按重要性排序）

- 难度判定补足 evidence_refs 计数：将 evidence_refs 数量纳入 bucket 判定规则，减少“hard 样本被误判为 high”。
  - 影响文件范围：`src/pipeline/steps/coverage_tagger.py`、`configs/launch.yaml`（阈值配置可选）。
  - 现有功能影响：低风险；分布会轻微调整。
- 生成侧多样性与场景化注入：引入 question_type 配额与“模糊/指代问”比例控制。
  - 影响文件范围：`configs/prompts/*`、`src/engine/auto_question_generator.py`、`src/engine/auto_design_question_generator.py`、`configs/launch.yaml`。
  - 现有功能影响：中风险；生成分布与文本风格变化，需要回归对比。
- Reasoning Trace 结构化一致性：补充 Analysis/Evidence/Decision 结构与 (File:L#Line) 锚定要求，并加入 trace-answer 一致性校验。
  - 影响文件范围：`configs/prompts/*`、`src/utils/validator.py`、`src/utils/schemas.py`。
  - 现有功能影响：中风险；格式更严格，可能提升 rejected 比例。
- Grounding 强化（调用链/依赖召回）：引入轻量依赖检索或调用链提示，降低跨模块漂移。
  - 影响文件范围：`src/engine/answer_generator.py`、`src/engine/design_generator.py`、`src/utils/vector_index.py` 或新增检索模块。
  - 现有功能影响：高风险；上下文召回策略变化影响质量与成本。
- 语义去重（embedding 相似度）：提升去重质量，降低模板化重复。
  - 影响文件范围：`src/utils/dedup.py` 或新增模块、`src/pipeline/steps/deduplication.py`。
  - 现有功能影响：中风险；计算成本上升。
- LLM-as-a-Judge + 回归：引入自动评分与 Bad Case 反馈闭环。
  - 影响文件范围：新增 judge 模块、report 输出、配置项扩展。
  - 现有功能影响：高风险；成本与依赖上升。

---

## 建议实施顺序（对现有功能影响最小 → 最大）

1) 难度判定补足 evidence_refs 计数  
2) 生成侧多样性与场景化注入  
3) Reasoning Trace 结构化一致性  
4) 语义去重（embedding 相似度）  
5) Grounding 强化（调用链/依赖召回）  
6) LLM-as-a-Judge + 回归机制
