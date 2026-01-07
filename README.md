# Intelligent Training Data Generation System

## What You Get

- **Two Scenarios**
  - 场景 1：`qa_rule`（基于业务流程/规则的问答对）
  - 场景 2：`arch_design`（基于仓库架构的设计方案）
- **Evidence-first**：样本通过 `thought.evidence_refs` 回指 `data/raw/extracted/symbols.jsonl`，支持一致性校验与审计
- **Auto RAG Mode（可选）**：方法画像 → embedding → 检索 → 生成问题与答案（质量与可控性更强）
- **Config-driven**：语言规则/分层识别通过 `configs/language/*.yaml` 扩展
- **Offline Pipeline**：Parse → (Auto/QA/Design) → Validation → Merge → Dedup → Safety → Split → Export

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

编辑 `configs/launch.yml`：

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

3) 选择生成模式（Auto 或标准）

```yaml
auto:
  embedding_model: "nomic-embed-text"
  max_methods: 50
  questions_per_method: 5

design_questions:
  use_method_profiles: true
```

### Run

```bash
python3 main.py
```

常用跳过项：

```bash
python3 main.py --skip-parse --skip-llm --skip-export
```

### Outputs（你应该看到）

- Parse：`data/raw/extracted/symbols.jsonl`、`data/raw/repo_meta/repo_meta.json`
- Intermediate：`data/intermediate/*.jsonl`
- Final SFT：`data/final/{train,val,test}_sft.jsonl`（以及 `data/final/qa/*`、`data/final/design/*`）
- Reports：`data/reports/pipeline_summary.json`、`data/reports/dataset_stats.json`

## Deep Dive（Design Docs）

基于 `src/pipeline` 的 step 拆分设计文档：

- 索引：`docs/pipeline/README.md`
- 编排与 Step API：`docs/pipeline/00-orchestrator-and-step-api.md`
- 各步骤：`docs/pipeline/01-parse-step.md` → `docs/pipeline/10-export-step.md`


## Roadmap

- **Quality Gate**：Validation 产出 `*_clean.jsonl`，让 Merge/后处理优先消费（从 report-only 升级为可训练强保证）
- **Artifact Contract Unification**：统一 step 与 engine 的输出路径/契约（由 Orchestrator `paths` 注入，消除默认路径漂移）
- **Scalable Retrieval**：把 JSONL embedding 索引升级为可选 FAISS/向量库，支撑大仓库
- **Dedup Upgrade**：引入 LSH/MinHash 并提供可解释的保留策略与评估
- **Parallel Generation**：LLM/embedding 阶段并发与重试、成本控制（batch/timeout/backoff）
- **More Languages**：扩展 JS/TS/Go 等语言（parser + language profile）
- **Evaluation Harness**：质量回归（schema pass rate、evidence 命中率、覆盖与多样性指标、泄漏风险评估）
