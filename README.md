# Intelligent Training Data Generation System

## What You Get

- **Two Scenarios**
  - 场景 1：`qa_rule`（基于业务流程/规则的问答对）
  - 场景 2：`arch_design`（基于仓库架构的设计方案）
- **Evidence-first**：样本通过 `thought.evidence_refs` 回指 `data/raw/extracted/symbols.jsonl`，支持一致性校验与审计
- **Auto RAG Mode（可选）**：方法画像 → embedding → 自动问题 → 回答（质量与可控性更强）
- **Config-driven**：语言规则/分层识别通过 `configs/language/*.yaml` 扩展
- **Offline Pipeline**：Parse → Method Understanding → Question/Answer → Design → Validation → Coverage Tagging → Coverage Sampling → Question Type Report → Merge → Dedup → Safety → Split → Export

## Getting Started

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

### Core Configuration（最重要的几项）

编辑 `configs/launch.yaml`：

1) 目标仓库与语言

```yaml
repo:
  path: "./repos/java/spring-ai"  # 改成你的仓库路径
  commit: ""                      # 可留空（自动从 git 取 HEAD）

language:
  name: "java"                    # java | python
  profile_dir: "configs/language"
```

2) 本地 LLM（Ollama）

```yaml
llm:
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5:7b"
  temperature: 0.2
  max_tokens: 10000
  timeout: 120
```

可选环境变量覆盖：

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

3) 选择生成模式（Auto QA / User QA）

```yaml
core:
  retrieval_top_k: 6
  max_context_chars: 16000

method_understanding:
  enabled: true
  max_methods: 10

question_answer:
  questions_per_method: 5
  max_questions: 25
  embedding_model: "nomic-embed-text"
  user_questions_path: "configs/user_inputs/user_questions.yaml"
  build_embeddings_in_user_mode: true

design_questions:
  use_method_profiles: true
  max_questions: 30
  user_questions_path: "configs/user_inputs/design_questions.yaml"
```

### Run

```bash
python3 main.py
```

常用跳过项：

```bash
python3 main.py --skip-parse --skip-llm --skip-export
```

Auto QA 开关：

```bash
# 默认开启 Auto QA
python3 main.py

# 使用用户问题（关闭 Auto QA）
python3 main.py --skip-question-answer
```

### Outputs（你应该看到）

- Parse：`data/raw/extracted/symbols.jsonl`、`data/raw/repo_meta/repo_meta.json`
- Intermediate：`data/intermediate/*.jsonl`
- Final SFT：`data/final/{train,val,test}_sft.jsonl`（以及 `data/final/qa/*`、`data/final/design/*`）
- Reports：`data/reports/pipeline_summary.json`、`data/reports/dataset_stats.json`、`data/reports/coverage_report.json`、`data/reports/question_type_report.json`

## Deep Dive（Design Docs）

基于 `src/pipeline` 的 step 拆分设计文档：

- 索引：`docs/pipeline/README.md`
- 编排与 Step API：`docs/pipeline/00-orchestrator-and-step-api.md`
- 各步骤：`docs/pipeline/01-parse-step.md` → `docs/pipeline/13-export-step.md`

Feature 说明文档（面向业务视角）：

- 索引：`docs/features/README.md`