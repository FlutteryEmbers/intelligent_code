# Java Parser 使用指南

## 概述

`JavaParser` 是基于 tree-sitter 的 Java 代码解析器，能够：

1. ✅ 递归扫描 Java 仓库中的所有 `.java` 文件
2. ✅ 提取类、方法、字段信息
3. ✅ 解析注解（特别是 Spring 注解）
4. ✅ 提取 JavaDoc 和注释
5. ✅ 智能截断过长的源码
6. ✅ 生成结构化的 `CodeSymbol` 对象

---

## 快速开始

### 1. 安装依赖

确保已安装必要的依赖：

```bash
pip install tree-sitter tree-sitter-java
```

### 2. 运行测试

```bash
# 测试简单 Java 代码解析
python test_java_parser.py
```

### 3. 解析真实仓库

#### 方式 1：使用配置文件

编辑 `configs/pipeline.yaml`：

```yaml
repo:
  path: "D:/path/to/your/java/repo"  # 修改为实际路径

parser:
  max_chars_per_symbol: 12000  # 单个符号最大字符数
  ignore_paths:
    - "test"
    - "tests"
    - "target"
    - "build"
```

然后运行：

```bash
python test_java_parser.py
```

#### 方式 2：使用代码

```python
from src.parser import JavaParser, get_repo_commit

# 初始化解析器
parser = JavaParser()

# 获取 commit
commit = get_repo_commit("/path/to/repo")

# 解析仓库
symbols = parser.parse_repo("/path/to/repo", commit)

print(f"解析完成：{len(symbols)} 个符号")
```

---

## API 参考

### JavaParser 类

```python
class JavaParser(BaseParser):
    def __init__(self, config: dict | None = None)
    def parse_repo(self, repo_path: str, repo_commit: str) -> list[CodeSymbol]
    def parse_file(self, file_path: Path, repo_commit: str, repo_root: Path | None = None) -> list[CodeSymbol]
```

#### 初始化参数

```python
config = {
    'max_chars_per_symbol': 12000,  # 单个符号最大字符数
    'ignore_paths': ['test', 'target'],  # 忽略的路径模式
}

parser = JavaParser(config=config)
```

#### parse_repo()

解析整个仓库：

```python
symbols = parser.parse_repo(
    repo_path="/path/to/java/repo",
    repo_commit="abc123def456"
)
```

**返回**：`list[CodeSymbol]` - 所有解析出的符号

**副作用**：
- 创建 `data/raw/extracted/symbols.jsonl`
- 创建 `data/raw/repo_meta/repo_meta.json`
- 创建 `data/reports/parsing_report.json`

---

## 支持的 Spring 注解

JavaParser 能够识别并解析以下 Spring 注解：

### 组件注解
- `@RestController`
- `@Controller`
- `@Service`
- `@Repository`
- `@Component`
- `@Configuration`

### 映射注解
- `@GetMapping`
- `@PostMapping`
- `@PutMapping`
- `@DeleteMapping`
- `@RequestMapping`

### 参数注解
- `@RequestParam`
- `@PathVariable`
- `@RequestBody`
- `@ResponseBody`

### 其他注解
- `@Transactional`
- `@Async`
- `@Scheduled`
- `@Autowired`
- `@Value`
- `@Qualifier`
- `@Bean`

---

## 输出格式

### 1. symbols.jsonl

每行一个 CodeSymbol JSON 对象：

```json
{
  "symbol_id": "src/Example.java:com.example.Example.hello:10",
  "symbol_type": "method",
  "name": "hello",
  "qualified_name": "com.example.Example.hello",
  "file_path": "src/Example.java",
  "start_line": 10,
  "end_line": 15,
  "source": "public String hello(@RequestParam String name) { ... }",
  "doc": "/**\n * 获取问候消息\n */",
  "annotations": [
    {
      "name": "GetMapping",
      "arguments": {"value": "\"/hello\""},
      "raw_text": "@GetMapping(\"/hello\")"
    }
  ],
  "metadata": {
    "class_name": "Example",
    "method_name": "hello",
    "has_annotations": true,
    "has_javadoc": true
  },
  "repo_commit": "abc123",
  "source_hash": "def456..."
}
```

### 2. repo_meta.json

仓库元数据：

```json
{
  "repo_path": "/path/to/repo",
  "repo_commit": "abc123def456",
  "total_files": 150,
  "parsed_files": 148,
  "failed_files": 2,
  "total_symbols": 1250,
  "symbols_by_type": {
    "method": 1000,
    "field": 200,
    "class": 50
  },
  "errors": [],
  "parsing_time_seconds": 45.2,
  "created_at": "2026-01-03T12:00:00+00:00"
}
```

### 3. parsing_report.json

详细的解析报告（与 repo_meta.json 相同格式）。

---

## 源码截断策略

当方法源码超过 `max_chars_per_symbol`（默认 12000 字符）时：

### 截断策略

保留头部和尾部，中间用标记替代：

```java
public void longMethod() {
    // 头部 6000 字符...
    
... /* TRUNCATED: 50000 chars omitted */ ...

    // 尾部 6000 字符...
}
```

### 元数据标记

```json
{
  "metadata": {
    "truncated": true,
    "original_chars": 68000
  }
}
```

---

## 错误处理

### 解析跳过记录

无法解析的项会记录到 `data/raw/extracted/parse_skipped.jsonl`：

```json
{
  "timestamp": "2026-01-03T12:00:00Z",
  "file_path": "src/Problem.java",
  "location": "com.example.Problem.buggyMethod",
  "reason": "Failed to extract method name"
}
```

### 文件级错误

文件级错误会记录在 `ParsingReport.errors` 中：

```json
{
  "file": "src/Broken.java",
  "error": "UnicodeDecodeError: ...",
  "type": "UnicodeDecodeError"
}
```

---

## 配置选项

### 通过配置文件

`configs/pipeline.yaml`:

```yaml
parser:
  type: "java"
  max_chars_per_symbol: 12000
  include_private: false
  ignore_paths:
    - "test"
    - "tests"
    - "target"
    - "build"
    - ".git"
  file_extensions:
    - ".java"
```

### 通过代码

```python
config = {
    'max_chars_per_symbol': 15000,
    'ignore_paths': ['test', 'target', 'generated']
}

parser = JavaParser(config=config)
```

---

## 使用示例

### 示例 1：解析单个文件

```python
from pathlib import Path
from src.parser import JavaParser

parser = JavaParser()
file_path = Path("src/Example.java")

symbols = parser.parse_file(
    file_path=file_path,
    repo_commit="abc123",
    repo_root=Path(".")
)

for symbol in symbols:
    print(f"{symbol.qualified_name}: {len(symbol.source)} chars")
```

### 示例 2：统计注解使用

```python
from collections import Counter
from src.parser import JavaParser, get_repo_commit

parser = JavaParser()
symbols = parser.parse_repo("/path/to/repo", get_repo_commit("/path/to/repo"))

# 统计注解
all_annotations = []
for symbol in symbols:
    all_annotations.extend([a.name for a in symbol.annotations])

ann_counter = Counter(all_annotations)
print("Top 10 annotations:")
for ann, count in ann_counter.most_common(10):
    print(f"  @{ann}: {count}")
```

### 示例 3：查找 Spring Controller

```python
from src.parser import JavaParser

parser = JavaParser()
symbols = parser.parse_repo("/path/to/repo", "commit_123")

# 查找所有带 @RestController 的方法
rest_methods = []
for symbol in symbols:
    if symbol.symbol_type == 'method':
        # 检查类级别或方法级别的注解
        for ann in symbol.annotations:
            if ann.name in ['RestController', 'Controller', 'GetMapping', 'PostMapping']:
                rest_methods.append(symbol)
                break

print(f"Found {len(rest_methods)} REST API methods")
```

### 示例 4：导出为 DataFrame

```python
import pandas as pd
import json

# 读取 symbols.jsonl
symbols = []
with open('data/raw/extracted/symbols.jsonl', 'r') as f:
    for line in f:
        symbols.append(json.loads(line))

# 转换为 DataFrame
df = pd.DataFrame(symbols)

print(df[['name', 'qualified_name', 'symbol_type']].head())

# 统计
print("\nSymbol types:")
print(df['symbol_type'].value_counts())
```

---

## 性能优化

### 1. 并行处理（未来优化）

当前版本是串行处理，可以通过多进程优化：

```python
# 未来版本可能支持
parser = JavaParser(config={'parallel_workers': 4})
```

### 2. 增量解析

只解析修改的文件：

```python
# 需要自己实现增量逻辑
modified_files = get_modified_files()  # 从 git diff 获取

for file in modified_files:
    symbols = parser.parse_file(file, commit, repo_root)
```

### 3. 调整字符限制

减少 `max_chars_per_symbol` 可以加快处理速度：

```python
parser = JavaParser(config={'max_chars_per_symbol': 8000})
```

---

## 故障排查

### 问题 1：tree-sitter 安装失败

```bash
# 确保安装了 C++ 编译器
pip install --upgrade pip setuptools wheel
pip install tree-sitter tree-sitter-java
```

### 问题 2：找不到 Java 文件

检查 `ignore_paths` 配置，确保没有错误地忽略了目标文件。

### 问题 3：解析速度慢

- 减少 `max_chars_per_symbol`
- 增加 `ignore_paths` 忽略测试文件
- 确保 SSD 存储

### 问题 4：内存占用高

大型仓库可能需要较多内存，考虑：
- 分批处理
- 减少 `max_chars_per_symbol`
- 使用生成器模式

---

## 与其他组件集成

### 与 LLMClient 集成

```python
from src.parser import JavaParser
from src.engine import LLMClient

# 解析代码
parser = JavaParser()
symbols = parser.parse_repo("/path/to/repo", "commit_123")

# 为每个方法生成训练样本
client = LLMClient()
samples = []

for symbol in symbols[:10]:  # 示例：只处理前 10 个
    sample = client.generate_training_sample(
        system_prompt="你是一个 Java 代码分析专家",
        user_prompt=f"分析方法：\n{symbol.source}",
        scenario="qa_rule",
        repo_commit=symbol.repo_commit
    )
    samples.append(sample)
```

---

## 相关文档

- [BaseParser API](../src/parser/base.py)
- [CodeSymbol Schema](../src/utils/schemas.py)
- [配置管理](../src/utils/config.py)
- [项目结构](STRUCTURE.md)

---

**JavaParser 已完全实现并可用！** 🎉
