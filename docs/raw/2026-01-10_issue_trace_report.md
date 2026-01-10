# 问题追踪报告: QA Evidence Missing & Design Quantity Low
>
> 日期: 2026-01-10
> **Note**: Written to `docs/raw/` because `docs/logs/` is gitignored.

## 1. 核心业务流程分析

数据生成流程主要依赖 `AnswerGenerator` (QA) 和 `DesignGenerator` (架构设计)。两者均使用 `Retriever` 组件从代码库中获取相关上下文 (`CodeSymbol`)。

1. **Retrieve**: `Retriever.retrieve_relevant_symbols(query, symbols)` 尝试查找与问题/需求相关的代码。
2. **Generate**:
    - QA: `AnswerGenerator` 构建 Prompt，包含检索到的代码作为 Context，要求 LLM 生成答案并引用 Evidence。
    - Design: `DesignGenerator` 检查是否检索到足够的 Symbols，构建架构分层 Context，要求 LLM 生成设计方案。
3. **Validate**: `validator.py` 检查生成的 Sample 是否包含 `evidence_refs` (QA) 或满足数量要求 (Design)。

## 2. 潜在问题排查列表

| 可能性等级 | 潜在原因 | 涉及核心文件 |
| :--- | :--- | :--- |
| **High** | **检索模块 Fallback 机制过弱**: 当 Vector Embeddings 不存在时，`Retriever` 仅返回列表前 k 个文件。在一个典型的仓库中，前 k 个文件通常是无关的 (e.g. `main.java`, `utils.java`)，导致 Context 与 Query 极度不匹配。LLM 无法依据无关 Context 生成 Evidence 或 Design。 | `src/engine/rag/retriever.py` |
| Medium | Language Profile 配置缺失: 针对特定语言 (如 Python, Java) 的 Annotation/Keyword 配置不匹配，导致 `DesignGenerator` 无法识别 Controller/Service 层，且 `_balance_layers` 失效。 | `configs/language/*.yaml`, `src/utils/generation/language_profile.py` |
| Low | PyPath/Windows Path 兼容性问题: LLM 生成的 Evidence Path 格式与 `validator` 期望的格式不一致 (如 `/` vs `\`)，导致验证失败。虽然有 normalization 逻辑，但极端情况可能未覆盖。 | `src/utils/data/validator.py` |

## 3. 详细分析与修复建议

### 3.1 [High] 检索模块 Fallback 机制过弱

- **逻辑缺陷**:
    `Retriever.retrieve_relevant_symbols` 代码中：

    ```python
    if self.embeddings_path.exists():
        # ... vector search ...
    else:
        # Fallback to FIRST K symbols
        retrieved_symbols = symbols[:k]
    ```

    当用户未生成 Embeddings (常见于新项目或快速测试) 时，检索退化为“截取前几行”。这导致 QA 和 Design 的 Context 几乎必定与 Query 不相关。
  - **QA**: 上下文无关 -> LLM 无法引用代码 -> `evidence_refs` 为空 -> `EVIDENCE_MISSING` 报错。
  - **Design**: 上下文无关 -> `relevant_symbols` 质量极差或被后续逻辑过滤 -> `DesignGenerator` 放弃生成或生成被拒。

- **影响文件**:
  - `src/engine/rag/retriever.py`
  - (新增) `src/utils/retrieval/keyword.py` (拟新增)

- **修复方案**:
    引入轻量级 **BM25 / Keyword Search** 作为 Fallback。当 Embeddings 不存在时，使用基于 Token 匹配的检索算法，确保返回的 Symbols 至少包含 Query 中的关键词。

    ```python
    # 伪代码建议
    if self.embeddings_path.exists():
        # Vector search
    else:
        # NEW: Keyword/BM25 search
        retrieved_symbols = keyword_search(query, symbols, top_k=k)
        if not retrieved_symbols:
            retrieved_symbols = symbols[:k] # 最后的保底
    ```

### 3.2 [Medium] Language Profile 泛化能力不足

- 对于 Issue 1 (兼顾 Python)，需确保 Python Profile 配置了正确的 Decorators/Keywords。
- 对于 Issue 2 (Java Design)，确保 `DesignGenerator` 在无法识别特定层级时 (如非 Spring 项目)，依然能通过 Keyword 检索提供有用的 Symbols。

---
请确认修复方案以解决上述根本原因。
