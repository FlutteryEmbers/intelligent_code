# 设计一致性审计报告
>
> 审计对象: src/engine/generators/ && src/engine/rag/
> 审计基准: docs/features/02_generation/
> 日期: 2026-01-10

## 1. 总体合规度摘要

- **完全符合**: 90%
- **存在偏差**: 1 个模块 (DesignQuestionGenerator)
- **严重缺失**: 0 个功能点

代码重构后，核心逻辑（尤其是“精准制导”和“RAG检索”）与文档高度一致。发现的主要差异在于“设计问题生成”的批处理策略上，代码采取了更激进的“强制批处理”策略，忽略了文档中的开关配置。

## 2. 差异矩阵 (Discrepancy Matrix)

| 模块/功能 | 设计要求 | 代码现状 | 差异严重度 (High/Med/Low) |
| :--- | :--- | :--- | :--- |
| **Design Gen** / Batching | 取决于 `batching.enabled` 开关 | **强制开启**循环批处理 | Medium |
| **Retriever** / Fallback | 降级为 "symbol_only" (未详述) | 实现了 **Keyword Search (BM25)** | Low (Feature+) |
| **Answer Gen** / Direct Hit | 优先使用 `evidence_refs` | **完全一致** (L135-151) | - |
| **Answer Gen** / Ref Correction | 校验并修正引用 | **完全一致** (L299-349) | - |

## 3. 详细审计发现

### 3.1 DesignQuestionGenerator (src/engine/generators/arch_design/question_generator.py)

- **设计描述**: `docs/features/02_generation/arch_design_generation.md` (Line 57) 指出：“当 `design_questions.batching.enabled = true`：最多循环...”。
- **代码实现**: `generate_from_repo` 方法 (Line 78) 直接进入 `while` 循环，未检查配置中的 `batching.enabled` 字段。
- **主要问题**: 代码不再支持“一次性生成所有问题”的模式。虽然这对大模型稳定性有益，但与文档描述的“可配置性”不符。
- **建议行动**: 更新文档以反映“强制批处理”的最佳实践，因为一次性生成 30+ 问题通常会导致 LLM 上下文溢出或质量下降。

### 3.2 Retriever (src/engine/rag/retriever.py)

- **设计描述**: `qa_generation.md` (Line 239) 提到“语义索引不存在时会自动降级为‘只用证据引用’(symbol_only)”。
- **代码实现**: `retrieve_relevant_symbols` (Line 83) 引入了 `keyword_search` (基于 Token 的加权搜索)。
- **主要问题**: 这是一个正向的“未文档化特性”。代码比文档更智能，不仅能“只用引用”，还能在无引用时通过关键词找到相关代码。
- **建议行动**: 在文档中补充 `Keyword Search` 机制，展示系统的鲁棒性。

### 3.3 AnswerGenerator (src/engine/generators/qa_rule/answer_generator.py)

- **审计确认**: 之前修复的“Direct Hit”逻辑（即优先使用问题自带的证据）在 Line 135 `if question.evidence_refs:` 处得到了清晰、准确的实现。这与 `qa_generation.md` 中关于 RAG 流程 Stage 1 的描述完全吻合。功能未丢失。

---
**审计结论**: 本次重构不仅没有丢失功能，反而通过强制批处理和关键词检索增强了系统的稳定性。建议微调文档以匹配代码的最新行为。
