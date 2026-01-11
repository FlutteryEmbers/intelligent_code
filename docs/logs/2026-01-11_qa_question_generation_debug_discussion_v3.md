好的，福尔摩斯模式已开启。基于之前的分析，我们要验证的一号嫌疑人是：**3b 模型指令遵循能力不足，导致 evidence_refs 模板未被完整复制；切换 7b 后服从度提升，问题自然消失**。

## 0. Summarize
- 问题表述：切换到 7b 模型后 QA 不再出现 evidence_refs 缺字段，说明问题可能是模型能力/指令遵循差异导致。
- 问题类别：qa_question_generation

## 1. 回顾与聚焦
- 先前排除：模板加载逻辑正常（`test_prompt_loading` 通过）。
- 新证据：7b 模型运行后问题“好像解决”。
- Hypothesis A：3b 模型对长 prompt 的遵循度不足，尤其是 evidence_refs 完整复制要求；7b 改善指令遵循，导致字段齐全。

## 2. 取证请求（如何证明它是错的）
请提供以下任一证据来否定 Hypothesis A：
1) 3b 与 7b 同配置下的 **warnings 统计对比**（`question_generation_warnings.json` 或 JSONL 计数）。
2) 7b 生成的 `questions.jsonl` 中 evidence_refs 是否包含 `source_hash` 的样例。

如果 7b 仍缺 source_hash，或差异与模型无关，则 Hypothesis A 被否定。

## 3. 逻辑分支
- 若 **是/差异显著**：可将“模型服从度”作为主因，制定策略（提高模型等级或缩短 prompt）。
- 若 **否/无差异**：进入 Hypothesis B（例如 prompt 过长/截断或输出后处理异常）。

下一步请提供：3b 与 7b 的 warnings 计数或 7b 样例 evidence_refs。 
