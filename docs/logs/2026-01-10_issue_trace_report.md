# 问题追踪报告: Fuzzy Question Evidence Backfilling
>
> 日期: 2026-01-10

## 1. 核心业务流程分析

当前 `AnswerGenerator` 的工作流如下：

1. **Ingest**: `generate_from_questions` 读取 `questions.jsonl` (包含 `QuestionSample` 对象)。
2. **Process**: 对于 "Fuzzy Questions" (无 `evidence_refs`)，`_generate_answer` 调用 `Retriever` 获取相关代码符号。
3. **Generate**: LLM 基于检索到的 `context` 生成答案，并在 `thought` 字段中输出引用的证据 (`evidence_refs`)。
4. **Output**: 生成一个新的 `TrainingSample` 对象，写入 `auto_qa_raw.jsonl`。

**关键发现**: 数据流是**单向**的。输入的问题对象 (`QuestionSample`) 在内存中被处理，但检索到的证据**仅**被用于构建 Prompt 和生成最终的 `TrainingSample`。并没有任何逻辑将检索结果“回填”到原始的 `QuestionSample` 对象或源文件中。

## 2. 潜在问题排查列表

| 可能性等级 | 潜在原因 | 涉及核心文件 |
| :--- | :--- | :--- |
| High | **设计预期 (Immutable Input)**: 管道设计倾向于保持原始问题文件不可变，仅在下游产物中包含证据。 | `src/engine/generators/qa_rule/answer_generator.py` |
| Low | **功能缺失**: 也许曾计划回填但未实现。 | - |

## 3. 详细分析与修复建议

### 3.1 设计预期 (Immutable Input)

- **逻辑描述**: `AnswerGenerator` (Line 123) 接收 `question`，并在内部通过 Retrieval 获取 `relevant_symbols`。这些 symbols 被转换为 `available_evidence` 传给 LLM。最终生成的 `TrainingSample` (Line 231) 包含 `thought.evidence_refs` (LLM 选用的证据)，但原始 `question.evidence_refs` 保持为空。
- **影响文件**:
  - `src/engine/generators/qa_rule/answer_generator.py`
- **结论**: 当前系统**不会**为问题填充 `evidence_ref`。如果用户再次读取输入文件，它仍然是 Fuzzy 的。

- **修复/增强方案 (如果业务需要回填)**:
  如果目标是让 "Fuzzy Questions" 变成 "Grounded Questions" 并保存下来，需要修改 `generate_from_questions` 以支持回写或输出一个新的 "Enhanced Questions" 文件。

```python
# 伪代码建议 (针对 AnswerGenerator.py)
# 在从 retrieve_relevant_symbols 获取 evidence 后：
if not question.evidence_refs:
    # 填充检索到的 Top-K 作为候选证据
    question.evidence_refs = [EvidenceRef.from_symbol(s) for s in relevant_symbols]
    # 可选择将更新后的 question 写入一个新的 questions_with_evidence.jsonl
```
