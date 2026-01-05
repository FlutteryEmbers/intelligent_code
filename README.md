# 智能训练数据生成系统（Java 代码仓 → Qwen2.5 微调数据）

面向本地 Java 代码仓库的训练数据管道：解析代码、构建结构化上下文、结合 RAG 与本地 LLM 生成 QA/架构设计数据，并进行校验、去重、切分与导出。

## ✨ 关键能力

- Java 代码解析：tree-sitter 提取类/方法/注解/JavaDoc
- 数据建模：Pydantic 结构化样本（可追溯、可验证）
- QA 生成：带代码理解（Auto QA）或不带代码理解（标准 QA）两种模式
- 设计生成：带代码理解（Auto 需求）或不带代码理解（固定需求）两种模式
- 质量控制：字段完整性、证据引用校验、去重与分割
- 本地 LLM：Ollama + LangChain 调用，支持结构化输出与重试

## 🔧 关键依赖

- tree-sitter / tree-sitter-java：Java 语法树解析
- pydantic：数据模型与校验
- pyyaml：配置文件解析
- langchain-openai / langchain-core：LLM 接入与结构化输出
- ollama：本地模型服务

完整依赖见 `requirements.txt`。

## 🧠 本地模型与配置（必须）

本项目依赖本地 Ollama 模型服务，需提前安装并拉取模型。

```bash
ollama serve
ollama pull qwen2.5:7b
```

在 `configs/pipeline.yaml` 中配置：

```yaml
llm:
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5:7b"
  temperature: 0.7
  max_tokens: 10000
  timeout: 120
```

可选环境变量覆盖：

```bash
# Windows
set REPO_PATH=D:\path\to\java\repo
set OLLAMA_BASE_URL=http://localhost:11434
set OLLAMA_MODEL=qwen2.5:7b

# Linux/Mac
export REPO_PATH=/path/to/java/repo
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
```

自动需求生成与自动 QA 使用同一套本地模型配置，具体以 `configs/pipeline.yaml` 中 `llm.*` 为准。

## 📁 目录结构

```
intelligent_code_generator/
├── configs/                    # 配置文件
│   └── pipeline.yaml          # 管道配置
├── src/                       # 源代码
│   ├── parser/               # 代码解析器
│   ├── engine/              # 数据生成引擎
│   ├── pipeline/            # 管道编排与步骤
│   └── utils/               # 工具模块
├── tests/                    # 测试脚本
├── data/                     # 产物目录
│   ├── raw/                  # 原始解析产物
│   ├── intermediate/         # 中间结果
│   ├── final/                # 最终数据
│   └── reports/              # 统计与报告
├── logs/                     # 日志
├── requirements.txt
└── README.md
```

## 🚀 快速开始

### 1) 安装依赖

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

### 2) 配置代码仓路径

编辑 `configs/pipeline.yaml`：

```yaml
repo:
  path: "./repos/java/your_repo"
```

### 3) 解析 Java 仓库

```bash
python tests/test_java_parser.py
```

输出：
- `data/raw/extracted/symbols.jsonl`
- `data/raw/repo_meta/repo_meta.json`

### 4) 生成 QA 数据（场景 1）

**两种模式**：\n- **带代码理解（Auto 模式）**：先生成方法画像与问题，再做检索式回答\n- **不带代码理解（标准模式）**：直接从符号抽取候选方法生成 QA

```bash
python tests/test_qa_generator.py
python -m src.engine.qa_generator --max-samples 50
```

输出：
- `data/intermediate/qa_raw.jsonl`
- `data/intermediate/qa_rejected.jsonl`

### 5) 生成设计方案数据（场景 2）

**两种模式**：\n- **带代码理解（Auto 需求）**：先从代码自动生成需求，再生成设计方案\n- **不带代码理解（固定需求）**：使用 `configs/requirements.yaml` 的需求

```bash
python tests/test_design_generator.py
python -m src.engine.design_generator --max-samples 5
```

输出：
- `data/intermediate/requirements.jsonl`
- `data/intermediate/design_raw.jsonl`
- `data/intermediate/design_rejected.jsonl`

### 6) 运行完整管道

```bash
python main.py
```

支持跳过步骤：

```bash
python main.py --skip-parse --skip-qa --skip-design --skip-export
```

## 🧪 产物与格式

- 原始符号：`data/raw/extracted/symbols.jsonl`
- 中间结果：`data/intermediate/*.jsonl`
- 最终数据：`data/final/{train,val,test}_sft.jsonl`
- 报告汇总：`data/reports/pipeline_summary.json`

## ⚙️ 常用配置项（pipeline.yaml）

- `repo.path`：Java 仓库路径
- `llm.*`：本地 Ollama 模型配置
- `auto.enabled`：自动问题生成开关（true=启用 auto QA 模块）
- `auto_requirements.enabled`：自动需求生成开关（true=从代码生成需求）
- `qa_generator.*`：QA 生成参数
- `design_generator.*`：设计方案参数
- `auto_requirements.*`：需求自动生成参数
- `split.*`：训练/验证/测试切分比例

## 🩺 常见问题

- **LLM 输出无法解析**：检查 Ollama 服务状态与模型是否存在。
- **数据量太小导致切分异常**：增加样本量或调整 `split.group_by`。
- **生成速度慢**：降低 `max_samples` 或调整批处理参数。

## 📚 参考文档

- `docs/PIPELINE_ARCHITECTURE.md`
- `docs/QA_GENERATOR_GUIDE.md`
- `docs/DESIGN_GENERATOR_GUIDE.md`
- `docs/java_parser/JAVA_PARSER_GUIDE.md`
