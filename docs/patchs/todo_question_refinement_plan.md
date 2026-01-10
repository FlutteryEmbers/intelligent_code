# Plan: Question Refinement & Evidence Backfilling
>
> Status: Draft
> Date: 2026-01-10
> Context: 解决 "Fuzzy Questions" (无证据引用) 不稳定且难以用于 Retrieval 评估的问题。

## 1. 核心目标

构建一套机制，将“模糊问题 (Fuzzy Questions)” 转化为 “落地问题 (Grounded Questions)”，从而：

1. **建立基准**: 为 Retrieval 评估提供稳定的 Ground Truth (`evidence_refs`)。
2. **消除不确定性**: 确保训练数据中的 Question-Evidence 关系是固定的，而非每次运行时动态变化的。
3. **保持管道清洁**: 遵循 "Input Immutability" 原则，不直接修改原始输入文件。

## 2. 架构设计：Evolution Pipeline

引入一个新的 Pipeline 步骤或独立工具：`QuestionRefiner`。

### 2.1 工作流

```mermaid
graph LR
    A[user_questions.yaml] -->|Fuzzy Input| B(QuestionRefiner)
    B -->|Retrieval (Top-K)| C{Refinement Strategy}
    C -->|Auto-Approve Top-1| D[grounded_questions.jsonl]
    C -->|Human-in-the-Loop| E[pending_review.jsonl]
```

### 2.2 核心组件

#### `QuestionRefiner` (New Class)

- **输入**: `questions.jsonl` (包含无 `evidence_refs` 的问题)。
- **依赖**: 复用现有的 `Retriever` 组件。
- **逻辑**:
  1. 读取每个问题。
  2. 如果已有 evidence，跳过。
  3. 如果没有，调用 `retriever.retrieve_relevant_symbols(q, top_k=5)`。
  4. **策略选择**:
      - *Aggressive*: 直接选取 Top-1 或 Top-3 作为 "Correct Evidence"。
      - *Analytic*: 使用 LLM 再进行一轮 "Relevance Check"，确认检索结果真的回答了问题，再写入。
  5. 输出到新文件。

## 3. 实施步骤 (Todo)

- [ ] **Step 1: 原型开发**
  - 创建 `tools/refine_questions.py` 脚本。
  - 实现基础的 `load -> retrieve -> save` 循环。
- [ ] **Step 2: 质量控制**
  - 集成 LLM 校验器：`RefinerVerifier`。
  - 让 LLM 判断：“检索到的这段代码是否真的能回答这个问题？”
  - 如果 No，则标记该问题为 "Unanswerable" 或需要人工干预。
- [ ] **Step 3: 管道集成**
  - 更新 `launch.yaml`，允许配置 `question_refinement.enabled`。
  - 在 `QuestionAnswerStep` 之前插入 Refinement 阶段。

## 4. 预期产物

- 新生成文件: `data/processed/grounded_questions.jsonl`
- 该文件将作为后续 Training Pipeline 的**金标准输入**。

## 5. 风险与缓解

- **Risk**: Retriever 找错了，导致 Ground Truth 也是错的 (Garbage In, Garbage Out)。
- **Mitigation**:
  - 引入 `Step 2` 的 LLM Verifier。
  - 仅对 High Confidence 的结果进行自动落地。
  - 保留人工 Review 接口。
