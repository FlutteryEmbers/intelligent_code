# 快速参考

## 核心 API

### 配置管理
```python
from src.utils import config

# 获取配置值
repo_path = config.repo_path
model = config.ollama_model
batch_size = config.batch_size

# 点分路径访问
base_url = config.get("llm.base_url", "http://localhost:11434")
section = config.get_section("parser")

# 确保输出目录存在
config.ensure_output_dirs()
```

### 数据模型
```python
from src.utils import (
    CodeSymbol, TrainingSample, ReasoningTrace, 
    EvidenceRef, Annotation, sha256_text
)

# 创建代码符号
symbol = CodeSymbol(
    symbol_id=CodeSymbol.make_symbol_id("Main.java", "com.example.Main", 10),
    symbol_type="class",
    name="Main",
    qualified_name="com.example.Main",
    file_path="src/Main.java",
    start_line=10,
    end_line=50,
    source="public class Main { ... }",
    doc="/** Main class */",
    annotations=[],
    metadata={},
    repo_commit="abc123",
    source_hash=sha256_text("public class Main { ... }")
)

# 验证哈希
is_valid = symbol.validate_hash()  # True

# 创建证据引用
evidence = EvidenceRef(
    symbol_id=symbol.symbol_id,
    file_path=symbol.file_path,
    start_line=symbol.start_line,
    end_line=symbol.end_line,
    source_hash=symbol.source_hash
)

# 创建推理轨迹
reasoning = ReasoningTrace(
    observations=["使用了单例模式"],
    inferences=["这是一个全局配置类"],
    evidence_refs=[evidence],
    assumptions=["类是线程安全的"]
)

# 创建训练样本
sample = TrainingSample(
    scenario="qa_rule",
    instruction="这个类使用了什么设计模式？",
    context=symbol.source,
    thought=reasoning,
    answer="该类使用了单例模式...",
    repo_commit="abc123"
)

# 序列化为 JSON
json_str = sample.model_dump_json(indent=2)
```

### 解析器基类
```python
from src.parser import BaseParser
from pathlib import Path

class JavaParser(BaseParser):
    def parse_repo(self, repo_path: str, repo_commit: str) -> list[CodeSymbol]:
        symbols = []
        repo_path_obj = Path(repo_path)
        
        # 遍历 Java 文件
        for java_file in repo_path_obj.rglob("*.java"):
            # 检查是否应该忽略
            if self.should_ignore(java_file):
                continue
            
            # 解析文件（这里需要实现具体逻辑）
            file_symbols = self.parse_file(java_file, repo_commit)
            symbols.extend(file_symbols)
        
        return symbols
    
    def parse_file(self, file_path: Path, repo_commit: str) -> list[CodeSymbol]:
        # 使用 tree-sitter 解析文件
        # 提取类、方法、字段
        # 返回 CodeSymbol 列表
        pass
```

## 环境变量

```bash
# Windows PowerShell
$env:REPO_PATH = "D:\path\to\java\repo"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_MODEL = "qwen2.5:latest"
$env:LOG_LEVEL = "INFO"

# Linux/Mac
export REPO_PATH="/path/to/java/repo"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_MODEL="qwen2.5:latest"
export LOG_LEVEL="INFO"
```

## 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行演示
python main.py

# 运行特定模块（示例）
python -c "from src.utils import config; print(config.ollama_model)"

# 验证配置
python -c "from src.utils import config; config.ensure_output_dirs(); print('OK')"

# 启动 Ollama
ollama serve

# 拉取模型
ollama pull qwen2.5:latest

# 测试 Ollama
curl http://localhost:11434/api/tags
```

## 文件路径

```
配置文件：    configs/pipeline.yaml
环境变量：    .env
日志文件：    logs/pipeline.log
原始数据：    data/raw/extracted/
最终数据：    data/final/
报告：        data/reports/
```

## 数据模型字段

### CodeSymbol
```
symbol_id          稳定主键：{file_path}:{qualified_name}:{start_line}
symbol_type        "class" | "method" | "field" | "file"
name               符号名称
qualified_name     完全限定名
file_path          相对文件路径
start_line/end_line 行号范围（1-based）
source             源码片段
doc                JavaDoc/注释
annotations        注解列表
metadata           额外元数据
repo_commit        仓库 commit hash
source_hash        源码 SHA256
```

### TrainingSample
```
scenario           "qa_rule" | "arch_design"
instruction        指令/问题
context            上下文信息
thought            ReasoningTrace（结构化推理）
answer             答案/输出
repo_commit        数据来源 commit
quality            质量评估结果（dict）
created_at         创建时间
sample_id          样本唯一标识
```

### ReasoningTrace
```
observations       观察到的事实列表
inferences         基于观察的推断列表
evidence_refs      支持推理的证据引用列表
assumptions        做出的假设列表
```

## JSON 格式示例

### CodeSymbol
```json
{
  "symbol_id": "src/Main.java:com.example.Main:10",
  "symbol_type": "class",
  "name": "Main",
  "qualified_name": "com.example.Main",
  "file_path": "src/Main.java",
  "start_line": 10,
  "end_line": 50,
  "source": "public class Main { ... }",
  "doc": "/** Main class */",
  "annotations": [],
  "metadata": {},
  "repo_commit": "abc123",
  "source_hash": "def456..."
}
```

### TrainingSample (JSONL 格式)
```json
{"scenario": "qa_rule", "instruction": "这个方法的时间复杂度是多少？", "context": "public void sort(int[] arr) { ... }", "thought": {"observations": ["双重循环"], "inferences": ["O(n²)"], "evidence_refs": [...], "assumptions": ["输入长度为 n"]}, "answer": "时间复杂度为 O(n²)", "repo_commit": "abc123", "quality": {}, "created_at": "2026-01-03T...", "sample_id": "1a2b3c4d"}
```

## 错误排查

| 问题 | 解决方案 |
|------|---------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| FileNotFoundError (配置文件) | 确保 `configs/pipeline.yaml` 存在 |
| Ollama 连接失败 | 检查 `ollama serve` 是否运行 |
| Python 命令不存在 | 安装 Python 并添加到 PATH |
| 权限错误 | 使用管理员权限或修改目录权限 |

## 下一步

1. 修改 `configs/pipeline.yaml` 中的 `repo.path`
2. 启动 Ollama：`ollama serve`
3. 实现 `JavaParser`（参考 `src/parser/base.py`）
4. 实现 `SampleGenerator`
5. 运行完整管道

详细信息请查看：
- `README.md` - 项目说明
- `INSTALL.md` - 安装指南
- `STRUCTURE.md` - 结构详解
