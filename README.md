# Intelligent Training Data Generation System

面向业务与工程团队的离线训练集生成流水线，强调“证据可追溯、质量可控、分布可解释”。

## 🌟 核心概念：像“有质检的内容工厂”一样
> 就像生产线先有质检再出货，系统先抽取代码证据，再生成样本，并用质量与分布规则把关。

## 📋 运作基石（必要元数据）

- **涉及领地 (Code Context)**：
  - Pipeline 编排：`src/pipeline/orchestrator.py`, `src/pipeline/base_step.py`
  - 解析与证据：`src/pipeline/steps/parse.py`, `src/parser/*`
  - 方法理解：`src/pipeline/steps/method_understanding.py`, `src/engine/auto_method_understander.py`
  - 问答生成：`src/pipeline/steps/question_answer.py`, `src/engine/auto_question_generator.py`, `src/engine/answer_generator.py`
  - 设计生成：`src/pipeline/steps/design_generation.py`, `src/engine/auto_design_question_generator.py`, `src/engine/design_generator.py`
  - 质量与分布：`src/pipeline/steps/validation.py`, `coverage_tagger.py`, `coverage_sampler.py`, `question_type_report.py`
  - 后处理与导出：`merge.py`, `deduplication.py`, `secrets_scan.py`, `split.py`, `export.py`

- **执行准则 (Business Rules)**：
  - 每条样本必须带证据引用 `evidence_refs`，并与代码符号一致。
  - 质量校验会产出 clean 分支，合并时优先使用 clean。
  - 分布控制按 80/15/5 目标抽样，并输出分布报表与回归告警。
  - 推理记录结构化输出（observations/inferences/assumptions），用于质量审计。

- **参考证据**：
  - `data/raw/extracted/symbols.jsonl` 与 `repo_commit` 用于一致性校验。

## ⚙️ 仪表盘：我该如何控制它？

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `repo.path` | 代码仓路径 | 指定解析对象 | 指向目标仓库 |
| `language.name` | 语言类型 | 选择解析器 | java / python |
| `llm.model` | 生成模型 | 控制生成质量与成本 | `qwen2.5:7b` |
| `method_understanding.enabled` | 方法理解开关 | 是否产出方法画像 | demo 开启 |
| `question_answer.max_questions` | QA 问题上限 | 控制问答规模 | 25 |
| `design_questions.max_questions` | 设计问题上限 | 控制设计样本规模 | 30 |
| `quality.gate_mode` | 质量门禁 | gate / report | demo 可 report |
| `question_answer.coverage.targets` | QA 难度分布 | 高/中/难比例 | 0.8/0.15/0.05 |
| `safety.mode` | 敏感信息处理 | drop / sanitize / keep | demo 可 keep |
| `dedup.semantic.enabled` | 语义去重开关 | 是否开启语义去重 | demo 可关闭 |

## 🛠️ 它是如何工作的（逻辑流向）

```mermaid
flowchart TD
  A[解析代码] --> B[方法理解]
  B --> C[问答生成]
  B --> D[设计生成]
  C --> E[质量校验]
  D --> E
  E --> F[分布打标/抽样]
  F --> G[类型报表]
  G --> H[合并]
  H --> I[去重]
  I --> J[安全清洗]
  J --> K[切分]
  K --> L[训练格式导出]

  subgraph 业务规则
    E --> E1[证据一致性 + 结构化推理]
    F --> F1[80/15/5 分布目标]
    H --> H1[clean 优先 / gate 模式]
  end
```

## 📐 样本数量计算逻辑

### QA 样本数量决定链

```
1. MethodUnderstanding
   ├── 输入: symbols.jsonl 中的所有方法符号
   └── 输出: method_profiles.jsonl
       └── 数量限制: max_methods (默认 25)

2. AutoQuestionGenerator
   ├── 输入: method_profiles (最多 25 个)
   ├── 每个 profile 生成问题数: questions_per_method (默认 3)
   ├── 潜在问题数 = 25 × 3 = 75 个
   └── 输出限制: max_questions (默认 15)
       └── 实际输出: min(75, 15) = 15 个问题

3. AnswerGenerator
   ├── 输入: 15 个问题
   └── 输出: 每个问题生成 1 个答案 → 15 个 QA 样本
       └── 质量门禁后: 15 - rejected = 最终 QA 数
```

| 配置项 | 路径 | 默认值 | 作用 |
|--------|------|--------|------|
| `max_methods` | `method_understanding.max_methods` | 25 | 限制处理的方法数 |
| `questions_per_method` | `question_answer.questions_per_method` | 3 | 每个方法生成多少问题 |
| `max_questions` | `question_answer.max_questions` | 15 | QA 问题总数上限 |

**公式**:
```
最终 QA 数 = min(max_methods × questions_per_method, max_questions) - rejected
           = min(25 × 3, 15) - rejected
           = 15 - rejected
```

### Design 样本数量决定链

```
1. DesignQuestionGenerator
   ├── 输入: symbols.jsonl + method_profiles.jsonl (可选)
   ├── 输出: design_questions_auto.jsonl
   └── 数量限制: max_questions (默认 10)

2. DesignGenerator
   ├── 输入: 10 个设计问题
   ├── 每个问题生成 1 个设计样本
   └── 内部上限: max_samples (默认 50)
       └── 实际受限于设计问题数，通常是 10

3. 输出: 10 个 Design 样本
   └── 质量门禁后: 10 - rejected = 最终 Design 数
```

| 配置项 | 路径 | 默认值 | 作用 |
|--------|------|--------|------|
| `max_questions` | `design_questions.max_questions` | 10 | 设计问题总数上限 |
| `max_samples` | `core.max_items` | 50 | Design 样本内部上限 |
| `use_method_profiles` | `design_questions.use_method_profiles` | true | 是否用 profiles 增强 |

**公式**:
```
最终 Design 数 = min(design_questions_count, max_samples) - rejected
              = min(10, 50) - rejected
              = 10 - rejected
```

### 关键结论

1. **QA 瓶颈在 `max_questions`** — 即使 `max_methods × questions_per_method` 很大，最终也只输出 `max_questions` 个问题
2. **Design 瓶颈在 `design_questions.max_questions`** — `max_samples` 是内部保护，实际被设计问题数量限制
3. **如果要增加输出数量**：
   - QA: 提高 `question_answer.max_questions`
   - Design: 提高 `design_questions.max_questions`
4. **Rejected 样本不影响生成数量计算** — 它们是在生成后被质量门禁过滤的，而非预先减少生成目标

## 🧩 解决的痛点与带来的改变

- **以前的乱象**：样本随机生成、证据不可追溯、质量难以说明。
- **现在的秩序**：证据有锚定、质量有门禁、分布有报表与回归提示。

## 💡 开发者笔记

- Pipeline 默认串行执行，单步失败不会阻断后续步骤（便于 demo 跑通）。
- 关键输出：`data/reports/*`（质量与分布报表）、`data/final/*`（训练数据）。
- 详细功能说明请见：
  - `docs/features/README.md`
  - `docs/pipeline/README.md`

## 快速开始（保留项）

### 配置目标解析仓库

在 `configs/launch.yaml` 中设置目标仓库路径与可选 commit：

```yaml
repo:
  path: "./repos/java/spring-ai"
  commit: ""
```

测试仓库（示例）：

- https://github.com/spring-projects/spring-ai
- https://github.com/FlutteryEmbers/online_shopping_be
- https://github.com/dieudonneAwa/mini-chatGPT

### Prerequisites

- Python 3.10+
- 本地 Ollama（用于 LLM 与 embedding）

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### Install

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 环境变量（可选）

```bash
# Windows
set REPO_PATH=D:\path\to\repo
set OLLAMA_BASE_URL=http://localhost:11434
set OLLAMA_MODEL=qwen2.5:7b

# Linux/Mac
export REPO_PATH=/path/to/repo
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
```

### Run

```bash
python3 main.py
```

常用参数（CLI）：

- `--config`：指定配置文件（默认 `configs/launch.yaml`）
- `--skip-parse`：跳过解析
- `--skip-question-answer`：关闭 Auto QA（使用用户问题）
- `--skip-auto`：`--skip-question-answer` 的旧别名
- `--skip-auto-design-questions`：跳过自动设计问题生成
- `--skip-llm`：跳过所有 LLM 生成
- `--skip-qa`：跳过 QA 生成
- `--skip-design`：跳过设计生成
- `--skip-dedup`：跳过去重
- `--skip-safety`：跳过安全扫描
- `--skip-export`：跳过导出

示例：

```bash
# 指定配置文件
python3 main.py --config configs/launch.yaml

# 使用用户问题（关闭 Auto QA）
python3 main.py --skip-question-answer

# 快速跳过耗时步骤
python3 main.py --skip-parse --skip-llm --skip-export
```

### Outputs（你应该看到）

- Parse：`data/raw/extracted/symbols.jsonl`、`data/raw/repo_meta/repo_meta.json`
- Intermediate：`data/intermediate/*.jsonl`
- Final：`data/final/{train,val,test}_sft.jsonl`（以及 `data/final/qa/*`、`data/final/design/*`）
- Reports：`data/reports/pipeline_summary.json`、`data/reports/dataset_stats.json`、`data/reports/coverage_report.json`、`data/reports/question_type_report.json`
