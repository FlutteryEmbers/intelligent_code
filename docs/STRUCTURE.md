# 项目结构概览

```
intelligent_code_generator/
│
├── configs/                           # 配置文件目录
│   └── pipeline.yaml                 # 主配置文件（仓库路径、LLM 设置、输出目录等）
│
├── src/                              # 源代码目录
│   ├── __init__.py                   # 包初始化文件
│   │
│   ├── parser/                       # 代码解析器模块
│   │   ├── __init__.py              # 导出 BaseParser
│   │   └── base.py                  # 解析器抽象基类（定义 parse_repo 接口）
│   │
│   ├── engine/                       # 数据生成引擎模块（待实现）
│   │   └── __init__.py              # 占位文件
│   │
│   └── utils/                        # 工具模块
│       ├── __init__.py              # 导出所有工具类和函数
│       ├── schemas.py               # Pydantic 数据模型定义
│       │                            #   - CodeSymbol（代码符号）
│       │                            #   - TrainingSample（训练样本）
│       │                            #   - ReasoningTrace（推理轨迹）
│       │                            #   - EvidenceRef（证据引用）
│       │                            #   - Annotation（Java 注解）
│       │                            #   - ParsingReport（解析报告）
│       └── config.py                # 配置管理（读取 YAML + 环境变量覆盖）
│
├── data/                             # 数据目录（自动创建）
│   ├── raw/                         # 原始数据
│   │   ├── extracted/               # 解析后的代码符号（JSON）
│   │   └── repo_meta/               # 仓库元数据
│   ├── intermediate/                # 中间处理结果
│   ├── final/                       # 最终训练数据（JSONL）
│   └── reports/                     # 解析报告和统计
│
├── logs/                            # 日志文件（自动创建）
│   └── pipeline.log                 # 管道运行日志
│
├── .cache/                          # 缓存目录（可选，自动创建）
│
├── venv/                            # Python 虚拟环境（建议创建）
│
├── main.py                          # 主入口脚本（演示程序）
├── requirements.txt                 # Python 依赖列表
├── README.md                        # 项目说明文档
├── INSTALL.md                       # 安装和运行指南
├── LICENSE                          # 开源许可证
├── .gitignore                       # Git 忽略规则
└── .env.example                     # 环境变量示例
```

## 核心文件说明

### 1. 数据模型层 (`src/utils/schemas.py`)

定义了所有 Pydantic 数据模型，具备以下特性：

- **可追溯性**：每个符号都有 `symbol_id`、`repo_commit`、`source_hash`
- **可验证性**：提供 `validate_hash()` 方法验证源码完整性
- **结构化推理**：`ReasoningTrace` 避免自由文本 CoT，提供结构化字段
- **证据引用**：`EvidenceRef` 精确指向代码位置

关键模型：
```python
CodeSymbol          # 代码符号（类/方法/字段/文件）
TrainingSample      # 训练样本（instruction + context + thought + answer）
ReasoningTrace      # 推理轨迹（observations + inferences + evidence_refs）
EvidenceRef         # 证据引用（指向具体代码位置）
Annotation          # Java 注解
ParsingReport       # 解析报告
```

工具函数：
```python
sha256_text(text)   # 计算文本 SHA256
now_iso()           # 获取当前 UTC 时间
```

### 2. 解析器抽象层 (`src/parser/base.py`)

定义了 `BaseParser` 抽象基类，提供：

**抽象方法**（子类必须实现）：
```python
parse_repo(repo_path, repo_commit) -> list[CodeSymbol]
```

**工具方法**（已实现）：
```python
should_ignore(path) -> bool              # 路径过滤
truncate_source(source) -> str           # 源码截断
generate_report(...) -> ParsingReport    # 生成报告
```

**可选方法**（增量解析）：
```python
parse_file(file_path, repo_commit) -> list[CodeSymbol]
iter_source_files(repo_path) -> Generator[Path]
```

### 3. 配置管理层 (`src/utils/config.py`)

提供统一的配置管理，特性：

- **单例模式**：全局唯一配置实例
- **YAML + 环境变量**：支持环境变量覆盖配置文件
- **点分路径访问**：`config.get("llm.base_url")`
- **便捷属性**：`config.ollama_model`、`config.repo_path` 等

环境变量支持：
```
REPO_PATH, REPO_COMMIT          # 仓库配置
OLLAMA_BASE_URL, OLLAMA_MODEL   # LLM 配置
LLM_TEMPERATURE, LLM_MAX_TOKENS # LLM 参数
LOG_LEVEL                       # 日志级别
```

### 4. 主配置文件 (`configs/pipeline.yaml`)

包含以下配置节：

- `repo`: 仓库路径、分支、commit
- `parser`: 解析器类型、忽略路径、最大字符数
- `generation`: 批次大小、上下文数量、场景配置
- `llm`: LLM 提供商、地址、模型、参数
- `output`: 输出目录配置
- `quality`: 质量控制参数
- `logging`: 日志配置
- `advanced`: 高级配置（缓存、并行等）

### 5. 主入口 (`main.py`)

演示程序，展示：
1. 配置管理的使用
2. 数据模型的创建和序列化
3. 哈希验证机制
4. 目录自动创建
5. 抽象基类说明

## 数据流向

```
Java 代码仓库
    ↓
[BaseParser.parse_repo()]  ← 解析器（待实现 JavaParser）
    ↓
CodeSymbol 列表
    ↓
[持久化到 data/raw/extracted/]
    ↓
[SampleGenerator]  ← 生成引擎（待实现）
    ↓
TrainingSample 列表
    ↓
[QualityChecker]  ← 质量检查（待实现）
    ↓
[持久化到 data/final/]
    ↓
Qwen2.5 微调训练数据
```

## 扩展点

### 1. 实现 JavaParser
```python
from src.parser import BaseParser
import tree_sitter_java as tsjava

class JavaParser(BaseParser):
    def __init__(self, config=None):
        super().__init__(config)
        # 初始化 tree-sitter parser
        
    def parse_repo(self, repo_path, repo_commit):
        # 遍历 .java 文件
        # 使用 tree-sitter 解析
        # 提取类、方法、字段
        # 返回 CodeSymbol 列表
        pass
```

### 2. 实现 SampleGenerator
```python
from src.utils import CodeSymbol, TrainingSample

class SampleGenerator:
    def generate_qa_samples(self, symbols: list[CodeSymbol]) -> list[TrainingSample]:
        # 生成 QA 类型样本
        pass
    
    def generate_arch_samples(self, symbols: list[CodeSymbol]) -> list[TrainingSample]:
        # 生成架构设计类型样本
        pass
```

### 3. 实现 QualityChecker
```python
class QualityChecker:
    def check_sample(self, sample: TrainingSample) -> dict:
        # 检查样本质量
        # 返回质量评分
        pass
    
    def deduplicate(self, samples: list[TrainingSample]) -> list[TrainingSample]:
        # 去重
        pass
```

## 依赖关系

```
main.py
  ↓
src.utils.config ←─── configs/pipeline.yaml
  ↓                   ↓ (环境变量覆盖)
src.utils.schemas     os.environ
  ↓
src.parser.base
  ↓
[具体实现：JavaParser, SampleGenerator, etc.]
```

## 设计原则

1. **关注点分离**：数据模型、解析、生成、质量控制各司其职
2. **可追溯性**：所有数据都包含 `repo_commit` 和 `source_hash`
3. **可验证性**：提供哈希验证机制
4. **可扩展性**：抽象基类便于支持多语言
5. **配置驱动**：所有参数都可通过配置文件或环境变量调整
6. **类型安全**：使用 Pydantic 进行数据验证

## 下一步开发顺序

1. ✅ 数据模型（已完成）
2. ✅ 配置管理（已完成）
3. ✅ 解析器基类（已完成）
4. ⬜ JavaParser 实现（使用 tree-sitter-java）
5. ⬜ SampleGenerator 实现（集成 LangChain + Ollama）
6. ⬜ QualityChecker 实现（去重、质量评分）
7. ⬜ CLI 命令行工具
8. ⬜ 单元测试和集成测试
9. ⬜ 文档完善
