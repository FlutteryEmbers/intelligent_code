# Step 4 — DesignGenerationStep Design

## 章节与重点内容

- Architecture Overview：自动设计问题 + 设计回答生成
- Design Patterns：Question-Driven Generation、Artifact boundary
- Data Flow：`symbols.jsonl` + `design_questions` → `design_raw.jsonl`
- Modular Detail：Auto/User 设计问题、检索与 evidence 约束
- Trade-offs：质量/成本、自动问题失败回退

---

## Architecture Overview

### 职责边界（Single Responsibility）

DesignGenerationStep 的职责是：生成设计类训练样本（`scenario=arch_design`）。问题来源既可以是 Auto Design Questions，也可以来自用户配置。

### 执行模式

- **Auto 设计问题**：未设置 `--skip-question-answer` 且未设置 `--skip-auto-design-questions`
- **User 设计问题**：当 Auto 关闭或失败时回退到 `design_questions.user_questions_path`
- **Skip**：`--skip-design` 或 `--skip-llm`

### 输入/输出（Artifacts）

- 输入：
  - `symbols.jsonl`
  - `design_questions.user_questions_path`
- 输出：
  - `data/intermediate/auto_questions/design_questions.jsonl`（设计问题快照）
  - `data/intermediate/design_raw.jsonl`
  - `data/intermediate/rejected/design_rejected.jsonl`
  - `data/reports/design_retrieval_report.json`

---

## Data Flow

```mermaid
flowchart TD
  S[(symbols.jsonl)] --> QG[DesignQuestionGenerator]
  QG --> Q[(design_questions.jsonl)]
  U[(design_questions.yaml)] --> DG[DesignGenerator]
  Q --> DG
  S --> DG
  DG --> O[(design_raw.jsonl)]
  DG --> R[(design_rejected.jsonl)]
```

---

## Modular Detail

### Auto Design Questions

- 由 `DesignQuestionGenerator` 从 symbols + method_profiles 生成（若启用）。
- 生成失败会记录 warning 并回退到用户问题配置。

### 设计回答生成

- `DesignGenerator` 会保存设计问题快照（便于审计），并逐条生成样本。
- 检索/召回可用 `design_questions.retrieval` 配置；支持调用链扩展（弱规则）。
- 支持 negative sampling：`design_questions.coverage.negative_ratio` / `negative_types`。

### 约束注入

- `design_questions.constraints` 可启用“反例对比”与“架构约束”提示段。
- 设计问题可包含 `question_type` 与 `scenario_constraints`，影响 prompt 结构与样本风格。

---

## Prompt 说明（模板角色）

### 设计出题模板（DesignQuestionGenerator）

#### 🌟 核心概念
> 就像“设计题库模板”，保证问题结构与覆盖目标一致。

#### 📋 运作基石（元数据与规则）
- **存放位置**：`configs/prompts/design/auto_design_question_generation.txt`、`coverage_design_question_generation.txt`
- **工序位置**：DesignGenerationStep → Step 3a
- **推理模式**：覆盖约束驱动的结构化出题
- **核心准则**：JSON-only、`design_questions` 列表、证据来自 `evidence_pool`

#### ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务直观名称 | 调节它的效果 |
| :--- | :--- | :--- |
| `design_questions.prompts.question_generation` | 设计出题模板 | 控制问题结构 |
| `design_questions.prompts.coverage_generation` | 覆盖出题模板 | 增加覆盖约束 |

#### 🛠️ 逻辑流向图 (Mermaid)

```mermaid
flowchart TD
  A[symbols.jsonl] --> B[加载出题模板]
  B --> C[注入覆盖变量]
  C --> D[LLM 输出 design_questions]
```

#### 🧩 解决的痛点
- **以前的乱象**：设计问题难以标准化。
- **现在的秩序**：模板化出题，覆盖目标可控。

---

### 设计回答模板（DesignGenerator）

#### 🌟 核心概念
> 就像“设计方案写作规范”，保证输出结构统一。

#### 📋 运作基石（元数据与规则）
- **存放位置**：`configs/prompts/design/design_system_prompt.txt`、`design_user_prompt.txt`
- **工序位置**：DesignGenerationStep → Step 3b
- **推理模式**：证据锚定的结构化设计方案
- **核心准则**：JSON-only、answer 六段式、证据逐字复制

#### ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务直观名称 | 调节它的效果 |
| :--- | :--- | :--- |
| `design_questions.prompts.system_prompt` | 系统模板 | 固定结构 |
| `design_questions.prompts.user_prompt` | 用户模板 | 注入问题与证据 |

#### 🛠️ 逻辑流向图 (Mermaid)

```mermaid
flowchart TD
  A[design_questions] --> B[加载系统/用户模板]
  B --> C[注入证据与约束]
  C --> D[LLM 输出 design_raw.jsonl]
```

#### 🧩 解决的痛点
- **以前的乱象**：设计答案结构不一致。
- **现在的秩序**：结构固定、易审计。

---

## Coupling Points

- ValidationStep：依赖证据引用与 schema 完整性。
- CoverageTagger/Sampler：基于 `quality.coverage` 统计与抽样。
- MergeStep：默认读取 clean 或 raw 设计工件。

---

## Trade-offs

- Auto 设计问题提升多样性，但生成失败时需回退。
- Auto 与 User 的双路径提高灵活性，但需要明确配置与路径契约。
