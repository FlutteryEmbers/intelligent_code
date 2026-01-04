# LLM Client 实现完成

## 🎉 新增功能

已在现有项目骨架上成功实现本地 LLM 调用封装！

## 📦 新增/修改的文件

### 核心实现

1. **[src/engine/llm_client.py](../src/engine/llm_client.py)** ⭐ 新增
   - `LLMClient` 类：完整的 LLM 调用封装
   - `generate_training_sample()` 方法：结构化输出生成
   - 自动重试机制（最多 2 次）
   - 失败记录到 `rejected_llm.jsonl`
   - 内置自测代码（`if __name__ == "__main__":`）

2. **[src/utils/logger.py](../src/utils/logger.py)** ⭐ 新增
   - `LoggerManager` 类：统一日志管理
   - `get_logger()` 函数：便捷的日志器获取
   - 支持文件和控制台双输出

3. **[test_llm_client.py](../test_llm_client.py)** ⭐ 新增
   - 独立的测试脚本
   - 5 步完整测试流程
   - 友好的测试报告输出

### 配置更新

4. **[src/engine/__init__.py](../src/engine/__init__.py)** 🔧 修改
   - 导出 `LLMClient` 类

5. **[src/utils/__init__.py](../src/utils/__init__.py)** 🔧 修改
   - 导出 `get_logger` 和 `LoggerManager`

6. **[configs/pipeline.yaml](../configs/pipeline.yaml)** 🔧 修改
   - 更新 `llm.base_url` 为 `http://localhost:11434/v1`（OpenAI 兼容端点）
   - 更新 `llm.model` 为 `qwen2.5-coder-3b-instruct`

7. **[src/utils/config.py](../src/utils/config.py)** 🔧 修改
   - 支持 `LLM_TIMEOUT` 环境变量
   - `base_url` 自动添加 `/v1` 后缀
   - 更新默认模型名称

8. **[.env.example](../.env.example)** 🔧 修改
   - 更新 LLM 配置项
   - 添加详细注释

### 文档

9. **[docs/LLM_CLIENT_GUIDE.md](LLM_CLIENT_GUIDE.md)** ⭐ 新增
   - 完整的使用指南
   - API 参考
   - 故障排查
   - 最佳实践

## ✨ 核心特性

### 1. 结构化输出

使用 `PydanticOutputParser` 强制 LLM 输出符合 `TrainingSample` schema：

```python
from src.engine import LLMClient

client = LLMClient()
sample = client.generate_training_sample(
    system_prompt="你是一个 Java 代码分析专家",
    user_prompt="分析这段代码...",
    scenario="qa_rule",
    repo_commit="abc123"
)

# sample 自动验证为 TrainingSample 对象
print(sample.instruction)
print(sample.answer)
```

### 2. 自动重试机制

```
尝试 1: 原始提示词
  ↓ 失败（JSON 解析错误）
尝试 2: 强化提示："只输出合法 JSON，不要额外文字"
  ↓ 失败（ValidationError）
尝试 3: 再次强化提示
  ↓ 失败
记录到 rejected_llm.jsonl + 抛出 ValueError
```

### 3. 失败样本记录

所有无法解析的输出都会记录到 `data/intermediate/rejected_llm.jsonl`：

```json
{
  "timestamp": "2026-01-03T10:30:00Z",
  "system_prompt": "...",
  "user_prompt": "...",
  "raw_output": "模型的实际输出",
  "error": "ValidationError: Field required: 'instruction'",
  "model": "qwen2.5-coder-3b-instruct",
  "temperature": 0.7
}
```

### 4. 完整日志

```python
from src.utils import get_logger

logger = get_logger(__name__)
logger.info("Processing started")
logger.error("An error occurred", exc_info=True)
```

日志会同时输出到：
- 文件：`logs/pipeline.log`
- 控制台：`stdout`

### 5. 灵活配置

支持 3 种配置方式（优先级从高到低）：

```python
# 1. 构造函数参数
client = LLMClient(
    model="custom-model",
    temperature=0.5
)

# 2. 环境变量
# export OLLAMA_MODEL=qwen2.5-coder-3b-instruct

# 3. 配置文件
# configs/pipeline.yaml
```

## 🚀 快速测试

### 方式 1：运行模块自测

```bash
python -m src.engine.llm_client
```

### 方式 2：使用独立测试脚本

```bash
python test_llm_client.py
```

### 方式 3：Python 交互式测试

```python
from src.engine import LLMClient

client = LLMClient()
client.test_connection()  # 测试连接
```

## 📋 测试前准备

### 1. 安装依赖（如果还没有）

```bash
pip install -r requirements.txt
```

### 2. 启动 Ollama 服务

```bash
ollama serve
```

### 3. 拉取模型

```bash
# 方式 1：使用推荐的小模型（3B）
ollama pull qwen2.5-coder-3b-instruct

# 方式 2：使用其他模型
ollama pull qwen2.5:7b
```

### 4. 验证服务

```bash
curl http://localhost:11434/v1/models
```

应该返回可用模型列表。

## 💡 使用示例

### 基础用法

```python
from src.engine import LLMClient

# 初始化客户端
client = LLMClient()

# 构建提示词
system_prompt = "你是一个 Java 代码分析专家"
user_prompt = """
分析以下代码并生成训练样本：

```java
public class Example {
    public void hello() {
        System.out.println("Hello");
    }
}
```
"""

# 生成样本
try:
    sample = client.generate_training_sample(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        scenario="qa_rule",
        repo_commit="abc123"
    )
    
    print(f"✓ 样本生成成功")
    print(f"  Instruction: {sample.instruction}")
    print(f"  Answer: {sample.answer[:100]}...")
    
except ValueError as e:
    print(f"✗ 生成失败: {e}")
```

### 批量生成

```python
from tqdm import tqdm

code_snippets = [...]  # 代码片段列表
samples = []

for snippet in tqdm(code_snippets, desc="生成样本"):
    try:
        sample = client.generate_training_sample(
            system_prompt=system_prompt,
            user_prompt=f"分析代码：\n{snippet}",
            scenario="qa_rule",
            repo_commit="abc123"
        )
        samples.append(sample)
    except ValueError:
        continue  # 跳过失败的样本

print(f"成功生成 {len(samples)} 个样本")
```

### 自定义配置

```python
# 使用更低的 temperature 提高一致性
client = LLMClient(temperature=0.3)

# 使用更大的 max_tokens 允许更长的输出
client = LLMClient(max_tokens=4000)

# 使用不同的模型
client = LLMClient(model="qwen2.5:7b")
```

## 🔍 API 接口

### LLMClient

```python
class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,      # Ollama API 地址
        model: str | None = None,          # 模型名称
        temperature: float | None = None,  # 温度参数
        max_tokens: int | None = None,     # 最大 token 数
        timeout: int | None = None,        # 超时时间（秒）
    )
    
    def generate_training_sample(
        self,
        system_prompt: str,      # 系统提示词
        user_prompt: str,        # 用户提示词
        scenario: str = "qa_rule",           # 场景类型
        repo_commit: str = "unknown"         # 仓库 commit
    ) -> TrainingSample
    
    def test_connection(self) -> bool
```

## 🐛 故障排查

### 问题 1：连接失败

```bash
# 检查 Ollama 服务
ollama serve

# 测试连接
curl http://localhost:11434/v1/models
```

### 问题 2：模型未找到

```bash
# 列出已安装的模型
ollama list

# 拉取所需模型
ollama pull qwen2.5-coder-3b-instruct
```

### 问题 3：输出格式错误

查看 `data/intermediate/rejected_llm.jsonl` 了解详情：

```bash
# Windows PowerShell
Get-Content data/intermediate/rejected_llm.jsonl | Select-Object -Last 1 | ConvertFrom-Json

# Linux/Mac
tail -n 1 data/intermediate/rejected_llm.jsonl | jq .
```

### 问题 4：Python 模块导入错误

```bash
# 确保在项目根目录
cd d:\Codes\intelligent_code_generator

# 检查 Python 路径
python -c "import sys; print('\n'.join(sys.path))"
```

## 📊 输出示例

### 成功的样本

```json
{
  "scenario": "qa_rule",
  "instruction": "这个 Calculator 类提供了哪些数学运算功能？",
  "context": "public class Calculator { ... }",
  "thought": {
    "observations": ["类中定义了 add 和 subtract 方法"],
    "inferences": ["提供了基本的加减运算"],
    "evidence_refs": [],
    "assumptions": ["方法是公开的"]
  },
  "answer": "该 Calculator 类提供了两个基本数学运算功能：add() 用于加法，subtract() 用于减法。",
  "repo_commit": "abc123",
  "quality": {},
  "created_at": "2026-01-03T10:30:00.000000+00:00",
  "sample_id": "1a2b3c4d5e6f7g8h"
}
```

### 拒绝的样本

```json
{
  "timestamp": "2026-01-03T10:30:00Z",
  "system_prompt": "你是一个 Java 代码分析专家...",
  "user_prompt": "分析代码...",
  "raw_output": "这是一个计算器类...",  # 不是 JSON
  "error": "JSONDecodeError: Expecting value: line 1 column 1",
  "model": "qwen2.5-coder-3b-instruct",
  "temperature": 0.7
}
```

## 📈 性能指标

| 操作 | 预期时间 |
|------|---------|
| 初始化客户端 | < 1 秒 |
| 测试连接 | 1-3 秒 |
| 生成单个样本（3B 模型） | 5-15 秒 |
| 生成单个样本（7B 模型） | 10-30 秒 |

## 🎯 下一步

1. ✅ LLM 调用封装（已完成）
2. ⬜ 实现 `JavaParser`（基于 tree-sitter-java）
3. ⬜ 实现 `SampleGenerator`（编排 Parser + LLMClient）
4. ⬜ 实现 `QualityChecker`（质量评估和去重）
5. ⬜ 完整的端到端管道

## 📚 相关文档

- **[LLM Client 使用指南](LLM_CLIENT_GUIDE.md)** - 详细的 API 文档和最佳实践
- **[项目结构](../STRUCTURE.md)** - 项目架构说明
- **[快速参考](../QUICKREF.md)** - 常用命令和 API
- **[安装指南](../INSTALL.md)** - 环境配置

## ✅ 验证清单

- [x] `LLMClient` 类实现
- [x] `generate_training_sample()` 方法
- [x] Pydantic 输出解析器集成
- [x] 自动重试机制（最多 2 次）
- [x] 失败样本记录到 `rejected_llm.jsonl`
- [x] 日志工具实现
- [x] 配置管理更新
- [x] 环境变量支持
- [x] 自测代码
- [x] 独立测试脚本
- [x] 完整文档

---

**实现完成！** 🎉

现在您可以开始使用 `LLMClient` 生成训练样本了。
