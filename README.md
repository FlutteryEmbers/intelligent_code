# Intelligent Training Data Generation System

> 面向业务与工程团队的离线训练集生成流水线，强调“证据可追溯、质量可控、分布可解释”。

## 🌟 核心特性
1. **有质检的内容工厂**: 从代码解析到样本生成，步步有质检。
2. **证据可追溯**: 每一条问答都锚定具体代码行 (`evidence_refs`)。
3. **分布可控**: 按 80/15/5 难度目标抽样，确保训练集不偏科。

## � 快速开始

### 1. Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) (用于 LLM 与 embedding)

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### 2. Install

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. Run

在 `configs/launch.yaml` 配置好 `repo.path` 后：

```bash
python3 main.py
```

## 结果与资源 (Results & Assets)

如果想深入了解数据、中间处理产物以及详细的评估报告，请探索 `assets/` 目录。
我们在该数据集上微调的 Qwen2.5-Coder-1.5B 模型相比基座模型表现出显著提升。

### 📊 微调指标对比 (`assets/eval_fine_tuning_report.md`)

| Metric | Fine-tuned | Base | Diff |
| :--- | :--- | :--- | :--- |
| **BLEU** | **0.1689** | 0.0600 | +0.1089 |
| **RougeL** | **0.4274** | 0.2463 | +0.1811 |

> 📈 **解读**: BLEU 分数几乎翻了三倍，表明模型学会了领域特定的表达；RougeL 的大幅提升显示出结构化输出能力的增强。详见：[完整报告](assets/eval_fine_tuning_report.md)

## 📚 文档索引

为了保持轻量，我们将详细文档拆分如下：

- **🏗️ 架构与原理 (Architecture)**
  - 了解系统是如何工作的、核心工作流图解、逻辑流向等。
  - [👉 docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

- **📐 数据模型 (Data Models)**
  - 核心数据结构设计 (Schema)、跨模块契约、报表格式。
  - [👉 docs/DATA_MODEL.md](docs/DATA_MODEL.md)

- **📖 操作指南 (Guides)**
  - 分模块的独立运行与使用说明。
  - [👉 Fine-Tuning Guide](docs/guides/fine_tuning_guide.md): 模型微调与评估。
  - [👉 Data Validator Guide](docs/guides/data_validator_guide.md): 数据校验与可视化报告。

- **⚙️ 配置与运维 (Configuration)**
  - 仪表盘参数说明、CLI 命令行参数、环境变量、样本数量计算公式。
  - [👉 docs/CONFIGURATION.md](docs/CONFIGURATION.md)

- **🧩 功能特性 (Features)**
  - 按业务阶段（Ingestion, Generation, Quality...）索引的功能列表。
  - [👉 docs/features/README.md](docs/features/README.md)

- **🔧 流水线细节 (Pipeline)**
  - 每一个 Step 的具体实现细节。
  - [👉 docs/pipeline/README.md](docs/pipeline/README.md)

---
*Happy Training Data Generation!*
