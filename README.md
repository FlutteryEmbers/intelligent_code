# Intelligent Training Data Generation System

A training data pipeline for local code repositories: parse code, build structured context, generate QA/architecture design data using RAG and local LLM, with validation, deduplication, splitting, and export capabilities.

## ✨ Key Features

- **Multi-Language Support**: Java (tree-sitter) and Python (AST-based)
- **Flexible Language Rules**: Layer/marker recognition rules in YAML (configs/language/*.yaml)
- Data Modeling: Pydantic structured samples (traceable and verifiable)
- QA Generation: With code understanding (Auto QA) or standard mode
- Design Generation: With code understanding (Auto Requirements) or fixed requirements
- Quality Control: Field completeness, evidence validation, deduplication, and splitting
- Local LLM: Ollama + LangChain with structured output and retry support

## 🔧 Key Dependencies

- tree-sitter / tree-sitter-java: Java syntax tree parsing
- pydantic: Data models and validation
- pyyaml: Configuration file parsing
- langchain-openai / langchain-core: LLM integration with structured output
- ollama: Local model service

See `requirements.txt` for complete dependencies.

## 🧠 本地模型与配置（必须）

本项目依赖本地 Ollama 模型服务，需提前安装并拉取模型。

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
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

## 📁 Directory Structure

```
intelligent_code_generator/
├── configs/                    # Configuration files
│   ├── pipeline.yaml          # Pipeline configuration
│   ├── language/              # Language-specific rules
│   │   ├── java.yaml         # Java QA/Design markers
│   │   └── python.yaml       # Python QA/Design markers
│   └── prompts/              # LLM prompt templates
├── src/                       # Source code
│   ├── parser/               # Code parsers (Java, Python)
│   ├── engine/              # Data generation engines
│   ├── pipeline/            # Pipeline orchestration and steps
│   └── utils/               # Utility modules
├── tests/                    # Test scripts
├── data/                     # Output directory
│   ├── raw/                  # Raw parsing results
│   ├── intermediate/         # Intermediate results
│   ├── final/                # Final training data
│   └── reports/              # Statistics and reports
├── logs/                     # Logs
├── requirements.txt
└── README.md
```

## 🌐 Language Support

The system supports multiple programming languages via YAML-based language profiles.

### Supported Languages

| Language | Parser | QA Markers | Design Layers | Config File |
|----------|--------|------------|---------------|-------------|
| Java | tree-sitter | @Transactional, @Service, etc. | Controller/Service/Repository | configs/language/java.yaml |
| Python | AST (tree-sitter planned) | @route, @task, etc. | Views/Services/Repositories | configs/language/python.yaml |

### Switching Languages

Edit `configs/pipeline.yaml`:

```yaml
language:
  name: "java"  # or "python" - automatically selects parser
  profile_dir: "configs/language"
```

### Customizing Language Rules

Language profiles define:
- **Parsing Configuration**: File extensions, ignore patterns, max chars per symbol
- **QA Markers**: Annotations/decorators indicating business logic candidates
- **QA Scoring Weights**: How to prioritize methods for QA generation
- **Design Layers**: Patterns for controller/service/repository identification

Example structure (configs/language/java.yaml):

```yaml
language: java

# Parsing configuration (auto-applied when language is selected)
parsing:
  file_extensions: [".java"]
  ignore_paths: ["target", "build", ".gradle", ".idea"]
  max_chars_per_symbol: 12000
  include_private: false
  include_test: false

qa:
  markers:
    annotations: [Transactional, Service, GetMapping, PostMapping]
    decorators: []
    name_keywords: [handler, processor, manager]
    path_keywords: [controller, service]
  scoring:
    annotation_weight: 10
    doc_weight: 5
    name_keyword_weight: 1

design:
  layers:
    controller:
      annotations: [RestController, Controller]
      name_keywords: [controller, endpoint, api]
      path_keywords: [controller]
    service:
      annotations: [Service, Component]
      name_keywords: [service, manager, handler]
      path_keywords: [service]
    repository:
      annotations: [Repository]
      name_keywords: [repository, dao, mapper]
      path_keywords: [repository, dao]
```

#### Override for Project-Specific Needs

You can override profile defaults in `pipeline.yaml`:

```yaml
# Optional: Override language profile's parsing defaults
parser:
  max_chars_per_symbol: 20000  # Project needs longer symbols
  include_private: true         # Include private methods

filter:
  ignore_paths:
    - "custom_vendor"  # Additional project-specific ignore (merged with profile)
```

See `docs/LANGUAGE_EXTENSION.md` for detailed customization guide.

## 🚀 快速开始

### 1) 安装依赖

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

### 2) Configure Repository Path

Edit `configs/pipeline.yaml`:

```yaml
repo:
  path: "./repos/java/your_repo"  # or "./repos/python/your_repo"
  
language:
  name: "java"  # or "python" - automatically selects parser and rules
```

### 3) Parse Repository

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

## ⚙️ Common Configuration Options (pipeline.yaml)

- `repo.path`: Repository path (Java or Python)
- `language.name`: Language name ("java" or "python") - selects parser and rules from configs/language/{name}.yaml
- `language.profile_dir`: Directory containing language YAML profiles
- `llm.*`: Local Ollama model configuration
- `auto.enabled`: Auto question generation switch (true = enable Auto QA)
- `auto_requirements.enabled`: Auto requirement generation switch (true = generate from code)
- `qa_generator.*`: QA generation parameters
- `design_generator.*`: Design generation parameters
- `auto_requirements.*`: Automatic requirement generation parameters
- `split.*`: Train/validation/test split ratios

## 🩺 Troubleshooting

- **LLM output parsing error**: Check Ollama service status and model availability.
- **Insufficient data for splitting**: Increase sample count or adjust `split.group_by`.
- **Slow generation**: Reduce `max_samples` or adjust batch parameters.
- **No candidates found**: Check language profile rules match your codebase patterns.

## 📚 Documentation

- `docs/PIPELINE_ARCHITECTURE.md` - Overall architecture
- `docs/QA_GENERATOR_GUIDE.md` - QA generation workflow
- `docs/DESIGN_GENERATOR_GUIDE.md` - Design generation workflow
- `docs/LANGUAGE_EXTENSION.md` - How to add new languages or customize rules
- `docs/java_parser/JAVA_PARSER_GUIDE.md` - Java parser details
- `docs/llm_client/LLM_CLIENT_GUIDE.md` - LLM client usage
