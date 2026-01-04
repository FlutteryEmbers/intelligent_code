# 智能训练数据生成系统 - Qwen2.5 微调数据工程

基于本地 Java 代码仓库自动生成高质量 Qwen2.5 微调训练数据，使模型具备代码理解和架构设计能力。

## 🎯 项目目标

为 Qwen 2.5 系列模型微调自动生成高质量训练数据，使模型具备：
1. **回答本地代码仓业务流程和规则问题的能力**（场景 1 - QA 问答）
2. **基于代码仓架构给出设计方案的能力**（场景 2 - 设计方案）

## ✅ 已实现功能

该工程实现了完整的 MLOps 数据管道：
1. **代码解析** ✅：使用 tree-sitter 解析 Java 代码，支持注解、JavaDoc、方法签名提取
2. **数据建模** ✅：使用 Pydantic 2.x 构建可追溯、可验证的数据模型
3. **场景 1 - QA 生成器** ✅：智能选择业务方法，生成问答对（带推理轨迹）
4. **场景 2 - 设计生成器** ✅：基于 RAG 检索相关代码，生成 6 章节架构设计方案
5. **LLM 集成** ✅：封装 Ollama 调用，支持结构化输出和自动重试
6. **质量控制** ✅：自动校验 Schema、Evidence Refs、内容完整性

## 📁 目录结构

```
intelligent_code_generator/
├── configs/                    # 配置文件
│   └── pipeline.yaml          # 管道配置 ✅
├── src/                       # 源代码
│   ├── parser/               # 代码解析器
│   │   ├── __init__.py
│   │   ├── base.py          # Parser 抽象基类
│   │   └── java_parser.py   # Java 解析器 ✅ (600+ 行)
│   ├── engine/              # 数据生成引擎
│   │   ├── __init__.py
│   │   ├── llm_client.py    # LLM 客户端封装 ✅
│   │   ├── qa_generator.py  # 场景 1：QA 生成 ✅ (632 行)
│   │   └── design_generator.py  # 场景 2：设计生成 ✅ (850 行)
│   └── utils/               # 工具模块
│       ├── __init__.py
│       ├── schemas.py       # Pydantic 数据模型 ✅
│       ├── config.py        # 配置管理 ✅
│       └── logger.py        # 日志工具 ✅
├── tests/                    # 测试脚本
│   ├── test_java_parser.py  # Java 解析测试 ✅
│   ├── test_qa_generator.py # QA 生成测试 ✅
│   └── test_design_generator.py # 设计方案测试 ✅
├── data/                     # 数据目录
│   ├── raw/                 # 原始数据
│   │   ├── extracted/       # 解析后的代码符号 (symbols.jsonl)
│   │   └── repo_meta/       # 仓库元数据
│   ├── intermediate/        # 中间处理结果
│   │   ├── qa_raw.jsonl     # QA 成功样本
│   │   ├── qa_rejected.jsonl # QA 失败样本
│   │   ├── design_raw.jsonl  # 设计成功样本
│   │   ├── design_rejected.jsonl # 设计失败样本
│   │   └── requirements.jsonl # 需求列表
│   ├── final/              # 最终训练数据（合并去重后）
│   └── reports/            # 解析报告和统计
├── docs/                    # 详细文档
│   ├── project_requirement.md   # 项目需求文档
│   ├── SCHEMAS.md              # 数据结构设计
│   ├── JAVA_PARSER_GUIDE.md    # Java 解析器指南
│   ├── QA_GENERATOR_GUIDE.md   # QA 生成器指南
│   └── DESIGN_GENERATOR_GUIDE.md # 设计生成器指南
├── logs/                    # 日志文件
├── requirements.txt        # Python 依赖
└── README.md              # 本文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 安装核心依赖
pip install -r requirements.txt
```

### 2. 配置项目

编辑 `configs/pipeline.yaml`，至少需要修改以下字段：

```yaml
repo:
  path: "path/to/your/java/repo"  # 修改为你的 Java 项目路径

llm:
  base_url: "http://localhost:11434"  # Ollama 服务地址
  model: "qwen2.5:latest"             # 使用的模型
```

**环境变量覆盖**（可选）：

```bash
# Windows
set REPO_PATH=D:\path\to\java\repo
set OLLAMA_BASE_URL=http://localhost:11434
set OLLAMA_MODEL=qwen2.5:latest

# Linux/Mac
export REPO_PATH=/path/to/java/repo
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:latest
```

### 3. 启动 Ollama 服务

确保 Ollama 已安装并运行：

```bash
# 安装 Ollama（如果尚未安装）
# 访问 https://ollama.ai/ 下载

# 启动服务
ollama serve

# 拉取模型
ollama pull qwen2.5:7b

# 验证服务
curl http://localhost:11434/v1/models
```

### 4. 解析 Java 代码仓库

```bash
# 运行解析器（将生成 symbols.jsonl）
python tests/test_java_parser.py
```

**输出文件**：
- `data/raw/extracted/symbols.jsonl` - 所有解析的代码符号
- `data/raw/repo_meta/repo_meta.json` - 仓库元数据（commit、文件统计）

### 5. 生成场景 1 数据（业务规则问答）

```bash
# 测试运行（5 个样本）
python tests/test_qa_generator.py

# 完整生成（50 个样本）
python -m src.engine.qa_generator --max-samples 50
```

**输出文件**：
- `data/intermediate/qa_raw.jsonl` - 成功生成的 QA 样本
- `data/intermediate/qa_rejected.jsonl` - 失败样本（用于分析改进）

**示例输出**：
```json
{
  "scenario": "qa_rule",
  "instruction": "UserService.createUser 方法如何保证原子性？",
  "context": "@Transactional\npublic User createUser(UserDTO dto) {...}",
  "answer": "通过 @Transactional 注解确保原子性，失败时自动回滚...",
  "thought": {
    "observations": ["方法标注了 @Transactional"],
    "inferences": ["使用 Spring 事务管理"],
    "evidence_refs": [{
      "symbol_id": "UserService.createUser(...)",
      "file_path": "src/main/java/com/example/UserService.java",
      "start_line": 15,
      "end_line": 30
    }],
    "assumptions": ["数据库支持事务"]
  }
}
```

### 6. 生成场景 2 数据（架构设计方案）

```bash
# 测试运行（2 个样本）
python tests/test_design_generator.py

# 完整生成（5 个需求）
python -m src.engine.design_generator --max-samples 5
```

**输出文件**：
- `data/intermediate/requirements.jsonl` - 生成的需求列表
- `data/intermediate/design_raw.jsonl` - 成功生成的设计方案
- `data/intermediate/design_rejected.jsonl` - 失败样本

**示例输出**：
```json
{
  "scenario": "arch_design",
  "instruction": "为用户登录接口添加 Redis 缓存层",
  "context": "Controller: AuthController.login(...)\nService: AuthService.authenticate(...)",
  "answer": "1. 现状画像\n当前基于 Spring Boot + MyBatis...\n2. 方案概述\n引入 Spring Cache + Redis...",
  "thought": {
    "observations": ["当前无缓存", "登录请求频繁"],
    "inferences": ["需要缓存提升性能"],
    "evidence_refs": [
      {"symbol_id": "AuthController.login(...)", "file_path": "..."},
      {"symbol_id": "AuthService.authenticate(...)", "file_path": "..."}
    ]
  }
}
```

### 7. 查看产物

生成的数据保存在以下位置：

- `data/raw/extracted/` - 解析后的代码符号
- `data/intermediate/qa_raw.jsonl` - 场景 1 成功样本
- `data/intermediate/design_raw.jsonl` - 场景 2 成功样本
- `logs/` - 完整运行日志

## 📊 两大场景对比

| 维度 | 场景 1 - QA 问答 | 场景 2 - 设计方案 |
|------|------------------|-------------------|
| **输入** | 解析的代码符号 | 代码符号 + 结构化需求 |
| **选择策略** | 优先级评分（注解+关键词） | RAG 检索（过滤+关键词打分） |
| **上下文** | 单个方法 + 相关注解 | Controller + Service + Repository |
| **输出长度** | 200-500 字 | 800-1500 字（6 章节） |
| **Evidence Refs** | ≥1 | ≥2（跨层级） |
| **示例数量** | 50 个 | 5 个（每个需求 1 个） |

## 🔧 核心模块说明

### 1. Java 解析器 (`src/parser/java_parser.py`)

**功能**：
- 使用 tree-sitter 解析 Java AST
- 提取类、方法、字段、注解
- 支持 JavaDoc 提取
- 源码截断（12000 字符限制）

**关键方法**：
- `parse_repo()`: 递归解析仓库
- `_parse_method()`: 解析方法（含注解、参数、返回类型）
- `_extract_annotations()`: 解析 Spring 注解（@Transactional、@RestController 等）
- `_extract_javadoc()`: 提取 JavaDoc 注释

**详细文档**：[Java 解析器指南](docs/JAVA_PARSER_GUIDE.md)

### 2. QA 生成器 (`src/engine/qa_generator.py`)

**功能**：
- 智能选择业务方法（基于注解和关键词）
- 优先级评分（@Transactional=10分、@GetMapping=8分）
- 上下文构造（16000 字符限制）
- LLM 生成问答 + 推理轨迹
- 质量校验（evidence_refs 非空）

**关键方法**：
- `_select_candidates()`: 筛选候选方法
- `_build_context()`: 构造 LLM 上下文
- `_validate_sample()`: 校验生成质量

**详细文档**：[QA 生成器指南](docs/QA_GENERATOR_GUIDE.md)

### 3. 设计生成器 (`src/engine/design_generator.py`)

**功能**：
- 5 个内置需求（缓存、幂等、读写分离、限流、异步）
- 轻量 RAG：过滤 + 关键词打分 + Top-K 选择
- 层级平衡（Controller + Service + Repository）
- 6 章节方案（现状/方案/接口/迁移/测试/风险）
- 多证据引用（≥2 个）

**关键方法**：
- `_filter_candidates()`: 按 Controller/Service/Repository 过滤
- `_calculate_relevance_score()`: 关键词匹配打分
- `_retrieve_context()`: RAG 检索 Top-K
- `_balance_layers()`: 确保跨层级引用

**详细文档**：[设计生成器指南](docs/DESIGN_GENERATOR_GUIDE.md)

### 4. LLM 客户端 (`src/engine/llm_client.py`)

**功能**：
- 封装 Ollama 调用
- 结构化输出（强制 JSON Schema）
- 自动重试（2 次，逐步强化提示）
- 失败记录（rejected_llm.jsonl）

**使用示例**：
```python
from src.engine.llm_client import LLMClient
from src.utils.schemas import TrainingSample

client = LLMClient()
result = client.generate_structured(
    system_prompt="你是 Java 架构师",
    user_content="分析这段代码...",
    schema=TrainingSample
)
```

### 5. 数据模型 (`src/utils/schemas.py`)

**核心模型**：
- **TrainingSample**: 训练样本（instruction/context/answer/thought）
- **ReasoningTrace**: 推理轨迹（observations/inferences/evidence_refs/assumptions）
- **CodeSymbol**: 代码符号（symbol_id/file_path/source/annotations）
- **EvidenceRef**: 证据引用（symbol_id/file_path/start_line/end_line/source_hash）

**详细文档**：[数据结构设计](docs/SCHEMAS.md)

## 📈 数据质量保证

### 自动校验

1. **Schema 完整性**：所有字段必须存在且类型正确
2. **Evidence Refs**：
   - QA：≥1 个引用
   - Design：≥2 个引用（跨层级）
3. **内容长度**：
   - instruction: 10-500 字符
   - answer: 50-5000 字符
4. **源码哈希**：确保引用的代码未被修改

### 失败回收

所有失败样本记录到 `*_rejected.jsonl`：
```json
{
  "error": "thought.evidence_refs is empty",
  "raw_output": {...},
  "retry_count": 2
}
```

### 可追溯性

每个样本包含：
- **repo_commit**: Git commit 哈希
- **evidence_refs**: 精确到行号的代码引用
- **quality**: 校验结果和上下文统计

## 🎓 训练数据格式

### Qwen 2.5 微调格式转换

```python
def convert_to_qwen_format(sample: TrainingSample) -> dict:
    """转换为 Qwen 2.5 微调格式"""
    return {
        "messages": [
            {
                "role": "system",
                "content": f"你是 Java 架构师，基于以下代码回答问题。\n\n{sample.context}"
            },
            {
                "role": "user",
                "content": sample.instruction
            },
            {
                "role": "assistant",
                "content": sample.answer
            }
        ]
    }
```

**可选**：保留推理过程（thought）作为元数据。

## 🐛 故障排查

### 常见问题

1. **Ollama 连接失败**
   ```bash
   # 检查服务状态
   curl http://localhost:11434/v1/models
   
   # 重启服务
   ollama serve
   ```

2. **生成失败率高**
   - 查看 `*_rejected.jsonl` 中的错误
   - 调整 `temperature`（降低 → 更稳定）
   - 使用更大的模型（qwen2.5:14b）

3. **内存占用高**
   - 减小 `batch_size`
   - 减小 `max_context_chars`
   - 使用更小的模型（qwen2.5:3b）

### 日志分析

```bash
# 查看完整日志
cat logs/pipeline.log

# 筛选错误
grep "ERROR" logs/pipeline.log

# 筛选警告
grep "WARNING" logs/pipeline.log
```

## 📚 详细文档

| 文档 | 说明 |
|------|------|
| [项目需求](docs/project_requirement.md) | 完整需求文档 |
| [数据结构设计](docs/SCHEMAS.md) | Pydantic 模型详解 |
| [Java 解析器指南](docs/JAVA_PARSER_GUIDE.md) | tree-sitter 使用和配置 |
| [QA 生成器指南](docs/QA_GENERATOR_GUIDE.md) | 场景 1 实现细节 |
| [设计生成器指南](docs/DESIGN_GENERATOR_GUIDE.md) | 场景 2 + RAG 详解 |

## 🎯 下一步计划

- [ ] 实现 QualityChecker 模块（去重、过滤）
- [ ] 端到端 Pipeline 脚本
- [ ] 数据格式转换工具（Qwen 2.5 微调格式）
- [ ] 模型微调脚本和评估
- [ ] Web UI 可视化界面

## 📝 许可证

MIT License

---

**项目已完成核心功能，可开始生成训练数据！** 🚀
  "symbol_type": "class",
  "name": "Main",
  "qualified_name": "com.example.Main",
  "file_path": "src/Main.java",
  "start_line": 10,
  "end_line": 50,
  "source": "public class Main { ... }",
  "doc": "/** Main entry class */",
  "annotations": [],
  "metadata": {},
  "repo_commit": "abc123def456",
  "source_hash": "sha256..."
}
```

### TrainingSample 示例

```json开发进度

### ✅ 已完成

1. ✅ **数据模型**: 完整的 Pydantic schemas（可追溯、可验证）
2. ✅ **配置管理**: YAML + 环境变量双重配置
3. ✅ **解析器基类**: 抽象基类定义
4. ✅ **LLM 客户端**: 本地 Ollama 调用封装 ✨
5. ✅ **日志工具**: 统一日志管理 ✨

### ⬜ 待实现

1. ⬜ **JavaParser**: 基于 tree-sitter-java 的具体解析器
2. ⬜ **SampleGenerator**: 训练样本生成引擎（编排 Parser + LLMClient）
3. ⬜ **QualityChecker**: 质量评估和去重模块
4. ⬜ **CLI**: 命令行界面
5. ⬜  "evidence_refs": [...],
    "assumptions": ["输入数组长度为 n"]
  },
  "answer": "该排序方法的时间复杂度为 O(n²)...",
  "repo_commit": "abc123def456",
  "quality": {}
}
```

## 🛠️ 下一步开发

当前版本为骨架代码，后续需要实现：

1. **JavaParser**: 基于 tree-sitter-java 的具体解析器
2. **SampleGenerator**: 训练样本生成引擎
3. **QualityChecker**: 质量评估和去重模块
4. **CLI**: 命令行界面
5. **Tests**: 单元测试和集成测试

## 📝 许可证

见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**注意**：本项目仅为骨架代码，业务逻辑尚未完全实现。运行前请确保已按要求配置好环境。
