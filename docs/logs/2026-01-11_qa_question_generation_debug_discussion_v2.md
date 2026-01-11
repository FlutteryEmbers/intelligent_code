好的，福尔摩斯模式已开启。基于之前的分析，我们要验证的一号嫌疑人是：**warnings 文件是旧运行产物，使用的是“未更新模板”的 prompt**。

## 0. Summarize
- 问题表述：`test_prompt_loading` 通过，但 QA 仍全部提示 `evidence_refs missing required fields`；需要据此继续定位“为什么实际产出缺 source_hash”。
- 问题类别：qa_question_generation

## 1. 回顾与聚焦
- 最近日志：`docs/logs/2026-01-11_qa_question_generation_issue_trace_report_v3.md`
- 新证据：`test_prompt_loading` 成功，说明**模板加载逻辑与配置路径**是正确的。
- Hypothesis A：当前 warnings 是旧运行生成的（未使用新模板/未注入 available_evidence_refs）。

## 2. 取证请求（如何证明它是错的）
请提供以下任一证据来否定 Hypothesis A：
1) 重新运行 QA 出题（仅 QA），并确认 **最新** `question_generation_warnings.jsonl` 仍全部缺 `source_hash`；
2) 提供 warnings 文件的最新时间戳，证明它生成于模板更新之后。

如果“最新 warnings 仍缺 source_hash”，则 Hypothesis A 被否定，进入 Hypothesis B。

## 3. 逻辑分支
- 若 **否/旧文件**（确为旧运行）：更新结论为“warnings 不可用”，需要用新运行数据继续诊断。
- 若 **是/最新仍缺**：进入 Hypothesis B。

---

若进入 Hypothesis B，我会验证：**prompt 过长或 evidence block 位置过后，导致 LLM 忽略 source_hash**。届时需要你提供：
- 本次运行的 prompt 长度告警日志（是否超过 `core.max_context_chars`），或
- 一次实际 prompt 片段（包含 evidence block 与输出要求相对位置）。
