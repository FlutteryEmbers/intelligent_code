# QA 问答生成（QA Generation）

## 🌟 核心概念：像“出题 + 标准答案流水线”一样
> 就像考试先出题再写答案，系统先生成问题，再基于代码证据生成可追溯的标准回答。

## 📋 运作基石（必要元数据）

- **涉及领地 (Code Context)**：
  - `src/pipeline/steps/question_answer.py`
  - `src/engine/auto_question_generator.py`
  - `src/engine/answer_generator.py`
  - `src/utils/vector_index.py`
  - `configs/launch.yaml`
  - `configs/user_inputs/user_questions.yaml`
  - `configs/prompts/question_answer/*`
  - `configs/user_inputs/qa_scenario_templates.yaml`

- **执行准则 (Business Rules)**：
  - Auto 模式：先产出问题，再检索证据生成回答。
  - User 模式：读取用户问题，必要时仍可构建“语义索引”以辅助检索。
  - 问题与回答必须携带 `evidence_refs`，用于后续质量校验。
  - 可按“问题类型配额”生成，并按比例注入“模糊/指代型”场景。
  - 可生成负向样本（证据不足/错误前提/冲突说明）。

- **参考证据**：
  - `method_profiles.jsonl` 作为出题原材料，`method_embeddings.jsonl` 作为语义检索索引。

## ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `question_answer.questions_per_method` | 每个方法出题数 | 生成问题数量 | 3 |
| `question_answer.max_questions` | 总问题上限 | 控制整体规模 | 25 |
| `question_answer.batch_size` | 批量出题 | 控制并行批次 | 5 |
| `question_answer.user_questions_path` | 用户问题入口 | 读取人工输入问题 | 保持默认 |
| `question_answer.build_embeddings_in_user_mode` | 用户模式索引 | 无证据时也能检索 | demo 可开启 |
| `question_answer.embedding_model` | 语义索引模型 | 生成检索向量 | `nomic-embed-text` |
| `question_answer.retrieval.mode` | 检索模式 | hybrid / symbol_only | demo 用 symbol_only |
| `question_answer.retrieval.call_chain.enabled` | 调用链扩展 | 召回关联方法 | true |
| `question_answer.coverage.diversity.question_type_targets` | 问题类型配额 | 控制问题风格 | 保持默认 |
| `question_answer.coverage.scenario_injection.fuzzy_ratio` | 模糊问题比例 | 注入“这段代码”类问题 | 0.2 |
| `question_answer.coverage.negative_ratio` | 负样本比例 | 反向场景占比 | 0.1 |
| `question_answer.coverage.negative_types` | 负样本类型 | 证据不足/错误前提/冲突 | 按需选 |
| `question_answer.constraints.enable_counterexample` | 反例对比 | 要求“为何不选其他方案” | true |
| `question_answer.constraints.enable_arch_constraints` | 架构约束 | 引用约束清单 | true |
| `artifacts.auto_qa_raw_jsonl` | QA 输出 | 生成的问答样本 | 默认即可 |
| `artifacts.method_embeddings_jsonl` | 语义索引输出 | 检索索引文件 | 默认即可 |
| `artifacts.auto_answer_rejected_jsonl` | QA 拒绝记录 | 输出失败样本 | 默认即可 |

## Prompt 说明（模板角色）

### 模板：`configs/prompts/question_answer/auto_question_generation.txt` / `coverage_question_generation.txt`

#### 🌟 核心概念
> 就像标准化“出题模板”一样，确保每一批问题都符合配额与业务语义。

#### 📋 运作基石（元数据与规则）
- **存放位置**：`configs/prompts/question_answer/auto_question_generation.txt`（基础）/ `coverage_question_generation.txt`（带覆盖约束）
- **工序位置**：QuestionAnswerStep → AutoQuestionGenerator（问题生成）
- **变量注入**：`method_profile`、`source_code`、`questions_per_method`、`coverage_bucket`、`coverage_intent`、`question_type`、`scenario_constraints`、`constraint_strength`、`constraint_rules`、`symbol_id/file_path/start_line/end_line/source_hash`、`repo_commit`
- **推理模式**：约束驱动的结构化出题（配额 + 证据对齐）
- **核心准则**：
  - 必须输出严格 JSON 且数量固定
  - `evidence_refs` 必须逐字复制输入
  - 问题必须与 bucket/intent/question_type 对齐
  - 禁止 Markdown/附加说明

#### ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务直观名称 | 调节它的效果 |
| :--- | :--- | :--- |
| `question_answer.prompts.question_generation` | 基础出题模板 | 控制问题结构 |
| `question_answer.prompts.coverage_generation` | 覆盖出题模板 | 启用覆盖约束 |
| `question_answer.coverage.*` | 覆盖与场景规则 | 决定 bucket/intent/场景注入 |

#### 🛠️ 逻辑流向图 (Mermaid)

```mermaid
flowchart TD
  A[MethodProfile] --> B[加载出题模板]
  B --> C[注入覆盖与场景变量]
  C --> D[LLM 生成问题 JSON]
  D --> E[questions.jsonl]
```

#### 🧩 解决的痛点
- **以前的乱象**：问题风格不一致、分布不可控。
- **现在的秩序**：出题有模板、有配额、有证据约束。

---

### 模板：`configs/prompts/question_answer/auto_answer_generation.txt`

#### 🌟 核心概念
> 就像“标准答案模板”一样，回答必须带证据、结构一致、可审计。

#### 📋 运作基石（元数据与规则）
- **存放位置**：`configs/prompts/question_answer/auto_answer_generation.txt`
- **工序位置**：QuestionAnswerStep → AnswerGenerator（回答生成）
- **变量注入**：`question`、`context`、`available_evidence_refs`、`format_constraints`、`common_mistakes_examples`、`architecture_constraints`、`counterexample_guidance`
- **推理模式**：证据锚定的结构化回答（observations/inferences/assumptions）
- **核心准则**：
  - 仅输出 JSON，禁止 Markdown
  - `answer` 必须是字符串且包含 Rejected Alternatives
  - `thought.evidence_refs` 必须来自可用证据池
  - 结构化推理（observations/inferences/assumptions）

#### ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务直观名称 | 调节它的效果 |
| :--- | :--- | :--- |
| `question_answer.prompts.answer_generation` | 回答模板 | 决定答案结构 |
| `question_answer.constraints.*` | 反例/架构约束 | 强化回答可审计性 |
| `question_answer.retrieval.*` | 证据召回 | 控制可用证据池 |

#### 🛠️ 逻辑流向图 (Mermaid)

```mermaid
flowchart TD
  A[questions.jsonl] --> B[检索证据]
  B --> C[加载回答模板]
  C --> D[注入证据与约束]
  D --> E[LLM 输出答案 JSON]
  E --> F[auto_qa_raw.jsonl]
```

#### 🧩 解决的痛点
- **以前的乱象**：回答缺证据、结构随意。
- **现在的秩序**：回答结构统一、证据可追溯。

备注：

- `qa_system_prompt.txt` / `qa_user_prompt.txt` 当前未在代码中加载，属于历史模板。

## 🛠️ 它是如何工作的（逻辑流向）

```mermaid
flowchart TD
  A[method_profiles.jsonl] --> B[生成问题]
  U[user_questions.yaml] --> B
  B --> C[questions.jsonl]
  C --> D[语义检索/证据召回]
  D --> E[生成回答]
  E --> F[auto_qa_raw.jsonl]
  E --> G[auto_answer_rejected.jsonl]

  subgraph 业务规则
    B --> B1[问题类型配额 + 模糊场景注入]
    D --> D1[证据只能来自候选池]
    E --> E1[可生成负向样本规则]
  end
```

## 🧩 解决的痛点与带来的改变

- **以前的乱象**：问题来源不稳定，回答缺乏证据。
- **现在的秩序**：问题有配额、回答有证据、负样本可控。

## 💡 开发者笔记

- Auto 模式若缺少 `method_profiles.jsonl` 会失败。
- 语义索引不存在时会自动降级为“只用证据引用”。
- 回答必须带 `evidence_refs`，否则会被质量校验拦截。
