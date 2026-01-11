# Pipeline Rubric Review（当前代码对照）

以下为根据现有代码能力对 `docs/rubric_template.md` 的逐项填写与证据引用，并附上按重要性排序的改进清单。

---

## 1. 宏观分布控制（Distribution Control）

- 配额逻辑校验：满足。证据：`src/pipeline/steps/coverage_sampler.py` 按 targets 抽样；`src/engine/generators/qa_rule/question_generator.py` 与 `src/engine/generators/arch_design/question_generator.py` 上游 bucket/intent 抽取；`configs/launch.yaml` 的 `question_answer.coverage.targets` / `design_questions.coverage.targets`。
- 难度判定因子-模块跨度：满足。证据：`src/pipeline/steps/coverage_tagger.py` 的 `_infer_module_span`。
- 难度判定因子-evidence_refs 数量：满足。证据：`src/pipeline/steps/coverage_tagger.py` 的 `_apply_evidence_bucket` + `configs/launch.yaml` 的 `question_answer.coverage.evidence_refs` / `design_questions.coverage.evidence_refs`。
- 隐含约束/反直觉 Prompt 注入：部分满足。证据：`_build_constraint_rules`（`src/engine/generators/qa_rule/question_generator.py`、`src/engine/generators/arch_design/question_generator.py`）在 strong 约束中覆盖“隐含约束/历史兼容/边界条件”，但未显式模板化“反直觉”场景。
- 多样性采样（question_type 均衡）：满足。证据：`src/engine/generators/qa_rule/question_generator.py` / `src/engine/generators/arch_design/question_generator.py` 的 `_sample_question_type` + `configs/launch.yaml` 的 `coverage.diversity.question_type_targets`。
- 场景化注入（模糊/指代问）：部分满足。证据：`configs/prompts/qa_rule/scenario_rules.yaml` / `configs/prompts/arch_design/scenario_rules.yaml` + `_build_scenario_constraints`（`src/engine/generators/qa_rule/question_generator.py`、`src/engine/generators/arch_design/question_generator.py`）与 prompts 占位符 `{scenario_constraints}`；`configs/launch.yaml` 中 QA `fuzzy_ratio=0.2`，Design `fuzzy_ratio=0.15`。

---

## 2. 证据锚定与 Grounding

- 元数据提取准确性：满足。证据：`src/utils/data/validator.py` 校验 symbol_id/file_path/source_hash/commit，支持路径归一化。
- 上下文最小化逻辑：部分满足。证据：`core.retrieval_top_k` / `core.max_context_chars`；`question_answer.retrieval` 与 `design_questions.retrieval` 的 min_score/fallback；但未剔除无关代码块。
- 依赖关系/调用链召回：部分满足。证据：`src/utils/retrieval/call_chain.py` 的弱规则扩展 + `src/engine/generators/qa_rule/answer_generator.py` / `src/engine/generators/arch_design/design_generator.py` 使用 `expand_call_chain`，并由 `configs/launch.yaml` 的 `retrieval.call_chain` 控制。
- Trace 锚定强制要求：部分满足。证据：`configs/launch.yaml` 的 `quality.trace_rules.require_evidence_anchor` + `src/utils/data/validator.py` 的 `TRACE_EVIDENCE_ANCHOR`；但 prompt 仍未要求每步标注 (File:L#Line)。

---

## 3. 推理链路质量（Reasoning Trace Logic）

- 多步推理结构：部分满足。证据：`ReasoningTrace` 结构化 + `quality.trace_rules.require_trace_structure`（`src/utils/data/validator.py`），但未强制 Analysis/Evidence/Decision 结构。
- 反例对比：部分满足。证据：`configs/prompts/qa_rule/gen_a_user.txt` 与 `configs/prompts/arch_design/gen_s_user.txt` 已加入 counterexample 段落要求，但未对输出做强校验。
- 关联架构约束：部分满足。证据：`configs/prompts/common/arch_constraints.yaml` + `core.architecture_constraints_path` 注入 prompts，但未做一致性校验。
- 逻辑自洽校验：部分满足。证据：`quality.trace_rules.require_answer_alignment` + `src/utils/data/validator.py` 的 `TRACE_ANSWER_ALIGNMENT`（默认关闭）。

---

## 4. 健壮性与负样本（Robustness & Negative Samples）

- 拒答逻辑生成：部分满足。证据：QA `negative_types` 含 `insufficient_evidence` 且注入规则（`src/engine/generators/qa_rule/answer_generator.py` + `configs/launch.yaml`），Design 未开启对应类型。
- 纠错场景生成：部分满足。证据：QA `negative_types` 含 `wrong_premise` 且注入规则（`src/engine/generators/qa_rule/answer_generator.py` + `configs/launch.yaml`），Design 未开启对应类型。
- 冲突处理样本：满足。证据：`negative_types` 包含 `conflict_spec`。

---

## 5. 工程质量与清洗（Data Engineering）

- 长度过滤：部分满足。证据：`src/utils/data/validator.py` 的 min/max 长度阈值；是否拒绝取决于 `quality.fail_on_warnings`。
- 关键词黑名单：满足。证据：`src/pipeline/steps/secrets_scan.py` 支持 blacklist + keep/drop/sanitize。
- 语义去重：部分满足。证据：`src/utils/dedup.py` 的 `dedup_jsonl_by_semantic` + `src/pipeline/steps/deduplication.py` 的语义去重开关（`dedup.semantic.enabled` 默认关闭）。
- 敏感信息脱敏：满足。证据：`src/pipeline/steps/secrets_scan.py` 支持 sanitize。

---

## 6. 验证与闭环（Verification & Feedback）

- LLM-as-a-Judge 接口：未满足。证据：未实现 judge 或评分接口。
- 报表输出：满足。证据：`qa_quality.json` / `design_quality.json` / `coverage_report.json` / `question_type_report.json` / `qa_retrieval_report.json` / `design_retrieval_report.json` / `dedup_mapping.json`，以及 `tools/render_reports.py` 的分布一致性校验与去重可视化。
- 回归机制：未满足。证据：无针对 Bad Case 的重生成/定向微调逻辑。

---

## 已完成的改进（基于 docs/patchs）

- 难度判定补足 evidence_refs 计数：`coverage_tagger._apply_evidence_bucket` + `coverage.evidence_refs` 配置已落地。
- 生成侧多样性与场景化注入：question_type 配额抽样、`*_scenario_templates.yaml` 与 `{scenario_constraints}` 已接入生成器与 prompts。
- Reasoning Trace 结构化一致性：`quality.trace_rules` 新增结构、锚定与一致性开关；validator 已支持 `TRACE_EVIDENCE_ANCHOR` / `TRACE_ANSWER_ALIGNMENT`。
- Grounding 轻量调用链扩展：弱规则 `call_chain` 已接入 QA/Design 检索链路，并在报告中统计 `call_chain_expanded`。
- 语义去重能力：`dedup_jsonl_by_semantic` 已实现并接入 pipeline（默认关闭）。
- 报表可视化：`render_reports.py` 输出分组目录并新增去重图表；`question_type_report.json` 输出分布与回归告警。

---

## 待改进清单（按重要性排序）

- Reasoning Trace 结构化一致性深化：补充 Analysis/Evidence/Decision 结构与 (File:L#Line) 锚定要求，并默认开启 trace-answer 一致性校验。
  - 影响文件范围：`configs/prompts/*`、`src/utils/data/validator.py`、`configs/launch.yaml`。
  - 现有功能影响：中风险；格式更严格，可能提升 rejected 比例。
- Grounding 强化升级：弱规则 call_chain 已实现，后续引入 call_graph 或语言级解析降低误召回。
  - 影响文件范围：`src/utils/retrieval/call_chain.py`、`src/engine/generators/qa_rule/answer_generator.py`、`src/engine/generators/arch_design/design_generator.py`、可能新增解析产物。
  - 现有功能影响：中风险；召回质量与成本权衡。
- 语义去重启用与优化：当前默认关闭，建议在小样本验证后开启，并考虑缓存/批量优化。
  - 影响文件范围：`src/utils/dedup.py`、`src/pipeline/steps/deduplication.py`、`configs/launch.yaml`。
  - 现有功能影响：中风险；计算成本上升。
- LLM-as-a-Judge + 回归：引入自动评分与 Bad Case 反馈闭环。
  - 影响文件范围：新增 judge 模块、report 输出、配置项扩展。
  - 现有功能影响：高风险；成本与依赖上升。

---

## 建议实施顺序（对现有功能影响最小 → 最大）

1) Reasoning Trace 结构化一致性  
2) 语义去重启用与优化  
3) Grounding 强化升级  
4) LLM-as-a-Judge + 回归机制
