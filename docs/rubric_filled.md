# Pipeline Rubric Review（当前代码对照）

以下为根据现有代码能力对 `docs/rubric.md` 的逐项填写与证据引用，并附上按重要性排序的改进清单。

---

## 1. 宏观分布控制（Distribution Control）

- 配额逻辑校验：部分满足。证据：`src/pipeline/steps/coverage_sampler.py` 按 coverage targets 抽样；`src/engine/auto_question_generator.py` 与 `src/engine/auto_design_question_generator.py` 进行上游 bucket/intent 抽取。
- 难度判定因子-模块跨度：满足。证据：`src/pipeline/steps/coverage_tagger.py` 的 `_infer_module_span` 基于 evidence_refs 路径前缀。
- 难度判定因子-evidence_refs 数量：未满足。证据：`src/pipeline/steps/coverage_tagger.py` 的 `_infer_bucket` 未使用 evidence_refs 数量。
- 隐含约束/反直觉 Prompt 注入：未满足。证据：当前 prompt 仅加入 bucket/intent 约束（`configs/prompts/question_answer/auto_question_generation.txt`、`configs/prompts/design/auto_design_question_generation.txt`）。
- 多样性采样（question_type 均衡）：未满足。证据：`configs/prompts/question_answer/auto_question_generation.txt` 列出类型，但生成与抽样未按 question_type 配额控制。
- 场景化注入（模糊提问/指代问）：未满足。证据：无对应 prompt 约束或生成逻辑。

---

## 2. 证据锚定与 Grounding

- 元数据提取准确性：满足。证据：`src/utils/schemas.py` 定义 EvidenceRef；`src/utils/validator.py` 校验 symbol_id/file_path/source_hash/commit。
- 上下文最小化逻辑：部分满足。证据：`configs/launch.yaml` 有 `core.retrieval_top_k` 与 `core.max_context_chars`；但未剔除无关代码块。
- 依赖关系/调用链召回：未满足。证据：暂无调用图或依赖图检索逻辑。
- Trace 锚定强制要求：未满足。证据：prompt 未要求逐步推导标注 (File:L#Line)。

---

## 3. 推理链路质量（Reasoning Trace Logic）

- 多步推理结构：未满足。证据：`src/utils/schemas.py` 提供 ReasoningTrace，但未强制 Analysis/Evidence/Decision 结构。
- 反例对比：未满足。证据：未见 prompt 或生成逻辑要求“为什么不选其他方案”。
- 关联架构约束：未满足。证据：生成逻辑未显式引用现有架构约束集。
- 逻辑自洽校验：未满足。证据：无脚本验证 trace 与 answer 的一致性。

---

## 4. 健壮性与负样本（Robustness & Negative Samples）

- 拒答逻辑生成：未满足。证据：没有“证据不足拒答”样本生成策略。
- 纠错场景生成：未满足。证据：无“误导性问题”生成逻辑。
- 冲突处理样本：未满足。证据：未模拟“实现与文档不一致”的冲突样本。

---

## 5. 工程质量与清洗（Data Engineering）

- 长度过滤：部分满足。证据：`src/utils/validator.py` 依据 `quality.min_*` 生成 warning；是否拦截取决于 `quality.fail_on_warnings`。
- 关键词黑名单：未满足。证据：无“AI 免责声明”等黑名单过滤逻辑。
- 语义去重：部分满足。证据：`src/pipeline/steps/deduplication.py` 使用 SimHash；未使用 embedding 相似度。
- 敏感信息脱敏：满足。证据：`src/pipeline/steps/secrets_scan.py` 支持 drop/sanitize。

---

## 6. 验证与闭环（Verification & Feedback）

- LLM-as-a-Judge 接口：未满足。证据：未实现 judge 或评分接口。
- 报表输出：部分满足。证据：`data/reports/qa_quality.json`、`data/reports/design_quality.json`、`data/reports/coverage_report.json` 存在，但覆盖报告未包含 intent/module_span 分布。
- 回归机制：未满足。证据：无针对 Bad Case 的重生成/定向微调逻辑。

---

## 改进清单（按重要性排序）

- 覆盖分布闭环补全：`coverage_report` 增加 intent/module_span 分布与缺口建议；确保 coverage targets 在运行时生效。
  - 影响文件范围：`src/pipeline/steps/coverage_sampler.py`、`src/pipeline/steps/coverage_tagger.py`、`configs/launch.yaml`、`data/reports/coverage_report.json`。
  - 现有功能影响：低风险；主要是报告字段扩展与采样配置校验，分布更稳定。
- 生成侧“高频/中等/困难”语义约束增强：在 prompt 中补充隐含约束/反直觉样式，并引入 question_type 配额。
  - 影响文件范围：`configs/prompts/question_answer/auto_question_generation.txt`、`configs/prompts/design/auto_design_question_generation.txt`、`configs/launch.yaml`、生成器配置读取（`src/engine/auto_question_generator.py`、`src/engine/auto_design_question_generator.py`）。
  - 现有功能影响：中风险；生成分布与文本风格变化，需要回归对比。
- Grounding 强化：引入依赖/调用链召回或轻量级关系检索，提高跨模块问题的证据闭合能力。
  - 影响文件范围：`src/engine/answer_generator.py`、`src/engine/design_generator.py`、检索/索引组件（`src/utils/vector_index.py` 或新增模块）。
  - 现有功能影响：中高风险；上下文召回策略变化会影响生成质量与成本。
- Reasoning Trace 结构化与一致性校验：要求 Analysis/Evidence/Decision 结构，并自动比对结论与 answer。
  - 影响文件范围：`configs/prompts/*`、`src/utils/schemas.py`、`src/utils/validator.py`。
  - 现有功能影响：中风险；格式更严格，可能提升 rejected 比例。
- 负样本机制：增加证据不足拒答、误导性问题纠偏、实现与注释冲突样本。
  - 影响文件范围：问题生成器与 prompt（`src/engine/auto_question_generator.py`、`configs/prompts/question_answer/auto_question_generation.txt`、`configs/prompts/design/auto_design_question_generation.txt`）。
  - 现有功能影响：中风险；样本类型扩展，训练集分布与模型行为会改变。
- 质量清洗增强：补充关键词黑名单过滤与 embedding 语义去重。
  - 影响文件范围：`src/pipeline/steps/secrets_scan.py` 或新增过滤步骤、`src/pipeline/steps/deduplication.py`。
  - 现有功能影响：中风险；过滤更严格，样本量可能下降但信噪比提升。

---

## 建议实施顺序（对现有功能影响最小 → 最大）

1) 覆盖分布闭环补全（报表字段与采样配置校验）  
2) 质量清洗增强（先做关键词黑名单过滤）  
3) Reasoning Trace 结构化校验（可能提高 rejected）  
4) 生成侧语义约束增强（prompt 调整，分布与风格变化）  
5) 负样本机制（训练分布与行为变化）  
6) Grounding 强化（检索策略变化，影响最大）
