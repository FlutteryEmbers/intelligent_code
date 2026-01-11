好的，福尔摩斯模式已开启。基于之前的分析，我们要验证的一号嫌疑人是：**LLM 实际未被提示或未显著看到包含 source_hash 的 evidence_refs 模板块，导致只输出 4 字段**。

## 0. Summarize
- 问题表述：QA 出题阶段生成的 questions 全部被标记为 evidence_refs 缺字段（缺 source_hash），是否是因为模型“已经知道引用位置”所以省略字段？
- 问题类别：qa_question_generation

## 1. 回顾与聚焦
- 最近日志：`docs/logs/2026-01-11_qa_question_generation_issue_trace_report_v3.md`
- 证据要点：MethodProfile 中 source_hash 完整，但 warning 中 evidence_refs 100% 缺 source_hash。
- Hypothesis A：LLM 在实际运行时未看到/未遵循 evidence_refs 模板块（模板未加载、位置过后或被截断），导致字段省略。

## 2. 取证请求（如何证明它是错的）
请提供任一 warning 对应的**真实 Prompt 输入片段**（包含 evidence_refs 模板块），或确认以下任一证据：
1) 运行日志中**实际加载的模板名**（question_generation / coverage_generation）；
2) 该次调用的 user_prompt 中是否包含 `available_evidence_refs` 且含 `source_hash`。

如果你能证明模板块存在且位置靠前，但输出仍缺 source_hash，则 Hypothesis A 被否定。

## 3. 逻辑分支
- 若 **是/存在**（模板块存在）：讨论下一步修复（增加强制校验或缩短输入以提升遵循率）。
- 若 **否/不存在**（模板块缺失或位置靠后/被截断）：直接锁定模板/加载逻辑为主因。

下一步请提供：一次 QA 出题的 prompt 片段或日志（包含模板名与 evidence block）。
