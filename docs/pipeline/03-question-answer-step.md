# Step 3 — QuestionAnswerStep Design (Method-Level RAG)

## 章节与重点内容

- Architecture Overview：三段式 QA 链路（Embeddings → Questions → Answers）
- Design Patterns：RAG Pipeline、Strategy（profile 规则来自 language profile）、Artifact boundary
- Data Flow：`method_profiles.jsonl` / `user_questions.yaml` → `questions.jsonl` → `auto_qa_raw.jsonl`
- Modular Detail：embedding 构建、向量检索、证据引用约束
- Trade-offs：成本/质量、路径隐式耦合、向量索引的简化实现

---

## Architecture Overview

### 职责边界（Single Responsibility）

QuestionAnswerStep 的职责是：在未设置 `--skip-question-answer` 时，基于已生成的 `method_profiles.jsonl` 执行 QA 生成链路，并输出 `auto_qa_raw.jsonl`。方法级理解由独立的 MethodUnderstandingStep 负责。

### 执行模式

- **Auto QA 模式**：未设置 `--skip-question-answer` 且未设置 `--skip-llm/--skip-qa`
  - 产生 `auto_qa_raw.jsonl`（TrainingSample）
- **User QA 模式**：设置 `--skip-question-answer` 且未设置 `--skip-llm/--skip-qa`
  - 从 `configs/user_questions.yaml` 读取问题并生成 `auto_qa_raw.jsonl`
- **Disabled/Skipped**：显式 `--skip-qa` / `--skip-llm`

### 输入/输出（Artifacts）

- 输入：
  - `method_profiles.jsonl`（由 MethodUnderstandingStep 产出）
  - `symbols.jsonl`（用于构造上下文与证据）
  - 语言规则：language profile（用于回答格式约束）
  - `configs/user_questions.yaml`（User QA 模式）
- 输出（默认路径由配置键控制）：
  - `data/intermediate/method_embeddings.jsonl`
  - `data/intermediate/auto_questions/questions.jsonl`
  - `data/intermediate/auto_qa_raw.jsonl`
  - 各类 rejected/失败回收文件（便于调试）

---

## Design Patterns

### 1) RAG Pipeline（检索增强生成）

Question/Answer 模块把 QA 生成分解为：

1. **索引（将 profiles 向量化）** → embeddings
2. **提问（从 profile 生成多样化问题或加载用户问题）** → questions
3. **回答（检索 Top-K 方法作为上下文，生成带证据的回答）** → TrainingSample

该拆分把“选择什么问”和“如何答”解耦，使可控性、可观测性更强（每个阶段都有落盘工件可检查）。

### 2) Artifact-as-Interface

阶段间通过 JSONL 工件衔接（profiles/questions/embeddings），使链路可断点重跑、可回放。

### 3) Strategy via Language Profile

候选方法评分/业务标记、回答格式约束、常见错误示例等信息由 language profile 提供（Java/Python 可不同）。

---

## Data Flow

```mermaid
flowchart TD
  P[(method_profiles.jsonl)] --> C[vector_index.build_embeddings]
  P --> D[AutoQuestionGenerator]
  U[(user_questions.yaml)] --> Q[(auto_questions/questions.jsonl)]
  D --> Q
  C --> E[(method_embeddings.jsonl)]
  Q --> F[AnswerGenerator]
  E --> F
  F --> O[(auto_qa_raw.jsonl)]
```

### “DB”等价说明

- 训练数据生成的“持久层”是 `data/intermediate/*` 工件文件。
- 向量索引使用 `method_embeddings.jsonl` 作为“索引库”（无独立数据库或向量数据库依赖）。

---

## Modular Detail

### A1：Embedding 构建与索引格式

关键点：

- 以 `qualified_name + summary + business_rules + tags` 组装 embedding 文本。
- 使用 Ollama embeddings API 直接生成 embedding，并把向量写入 JSONL（每行一个 embedding entry）。
- 该实现是“轻量索引”，无需引入向量数据库，便于本地快速验证。

### A2：Question 生成与去重

关键点：

- 每个 profile 生成 `questions_per_method` 个问题。
- 使用简单 hash 去重（避免重复问题污染训练集多样性）。

### A3：Answer 生成（检索 Top-K 作为上下文）

关键点：

- 根据问题文本进行向量检索，取 Top-K methods 作为上下文拼接。
- 从检索到的方法构造 `available_evidence_refs`，并要求 LLM 选择其中的证据引用写入 `thought.evidence_refs`（这是后续 Validation/Split 的强契约）。
- 最终输出 `TrainingSample`（`scenario=qa_rule`）。

---

## Coupling Points（与后续步骤的耦合）

### 1) 与 MethodUnderstandingStep 的输入耦合

QuestionAnswerStep 依赖 `method_profiles.jsonl`，当 MethodUnderstandingStep 被关闭或未产出 profiles 时，Auto QA 会失败。

### 2) 与 MergeStep 的“路径/命名耦合”

MergeStep 会读取 `artifacts.auto_qa_raw_jsonl`（并兼容旧的 `qa_raw.jsonl`），因此 Question/Answer 模块输出路径必须与该配置保持一致。

### 3) 与 Split/Validation 的 schema 耦合

Auto 输出的 TrainingSample 必须包含 `thought.evidence_refs`（且 `symbol_id/source_hash/file_path/line` 与 symbols.jsonl 一致），否则：

- Validation 会报 evidence 缺失/不一致
- group split 会退化为 `_NO_EVIDENCE_` 分组，增加泄漏风险

---

## Trade-offs

### 1) 质量提升 vs 成本与吞吐

- 质量收益：问题多样性更强，上下文更相关，回答更可解释。
- 成本：需要多次 LLM 调用（profile+question+answer）以及 embedding 生成，整体耗时与资源显著增加。

### 2) 轻量索引 vs 工程化检索

- 优点：零外部依赖、易部署、适合本地快速验证。
- 代价：线性扫描 embeddings 的检索在规模上不具备可扩展性；未来可替换为 FAISS/向量 DB，并保持接口不变（`search(query) -> [(symbol_id, score)]`）。

### 3) 输出路径的隐式耦合

- 当前多数引擎通过 `Config` 读取输出路径；step 层未显式把 `paths` 注入引擎，导致路径契约更隐式。
- 建议演进：在 step 中显式传入输出路径，或统一由 Orchestrator 的 `paths` 生成并注入。

