# LLM Client 使用指南

## 概述

`LLMClient` 是本项目的 LLM 调用封装层，提供：

1. ✅ **OpenAI 兼容接口**：使用 `langchain_openai.ChatOpenAI` 对接本地 Ollama
2. ✅ **结构化输出**：强制返回符合 `TrainingSample` schema 的 JSON
3. ✅ **自动重试机制**：最多重试 2 次，逐步强化提示
4. ✅ **失败记录**：将无法解析的输出记录到 `rejected_llm.jsonl`
5. ✅ **完整日志**：记录所有调用过程和性能指标

## 快速开始

### 1. 启动 Ollama 服务

```bash
# 启动 Ollama 服务
ollama serve

# 拉取模型（如果还没有）
ollama pull qwen2.5-coder-3b-instruct
```

### 2. 验证服务可用

```bash
# 测试 Ollama API
curl http://localhost:11434/v1/models

# 应该返回可用模型列表
```

### 3. 初始化 LLMClient

```python
from src.engine import LLMClient

# 使用默认配置（从 configs/pipeline.yaml 读取）
client = LLMClient()

# 或手动指定配置
client = LLMClient(
    base_url="http://localhost:11434/v1",
    model="qwen2.5-coder-3b-instruct",
    temperature=0.7,
    max_tokens=2000,
    timeout=60
)
```

### 4. 测试连接

```python
if client.test_connection():
    print("✓ LLM 连接成功")
else:
    print("✗ LLM 连接失败")
```

### 5. 生成训练样本

```python
system_prompt = """你是一个 Java 代码分析专家。
根据给定的代码片段，生成一个训练样本。"""

user_prompt = """分析这段代码：

```java
public class Example {
    public void hello() {
        System.out.println("Hello");
    }
}
```

生成一个问答样本。"""

# 生成样本
sample = client.generate_training_sample(
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    scenario="qa_rule",
    repo_commit="abc123"
)

print(f"Instruction: {sample.instruction}")
print(f"Answer: {sample.answer}")
```

## API 参考

### LLMClient 类

#### `__init__(...)`

初始化 LLM 客户端。

**参数：**
- `base_url` (str, optional): Ollama API 地址，默认从配置读取
- `model` (str, optional): 模型名称，默认从配置读取
- `temperature` (float, optional): 温度参数（0.0-1.0），默认 0.7
- `max_tokens` (int, optional): 最大 token 数，默认 2000
- `timeout` (int, optional): 超时时间（秒），默认 60

**环境变量覆盖：**
- `OLLAMA_BASE_URL`: 覆盖 base_url
- `OLLAMA_MODEL`: 覆盖 model
- `LLM_TEMPERATURE`: 覆盖 temperature
- `LLM_MAX_TOKENS`: 覆盖 max_tokens
- `LLM_TIMEOUT`: 覆盖 timeout

#### `generate_training_sample(...)`

生成结构化训练样本。

**参数：**
- `system_prompt` (str): 系统提示词
- `user_prompt` (str): 用户提示词
- `scenario` (str): 场景类型（"qa_rule" 或 "arch_design"）
- `repo_commit` (str): 仓库 commit hash

**返回：**
- `TrainingSample`: 解析后的训练样本对象

**异常：**
- `ValueError`: 所有重试失败后抛出

**重试逻辑：**
1. 初次尝试使用原始提示词
2. 失败后自动重试（最多 2 次）
3. 重试时强化提示："只输出合法 JSON，不要额外文字"
4. 所有尝试失败后记录到 `rejected_llm.jsonl` 并抛出异常

#### `test_connection()`

测试 LLM 连接是否正常。

**返回：**
- `bool`: 连接是否成功

## 结构化输出机制

### Pydantic 输出解析器

使用 `PydanticOutputParser` 强制 LLM 输出符合 `TrainingSample` schema：

```python
from langchain_core.output_parsers import PydanticOutputParser
from src.utils.schemas import TrainingSample

parser = PydanticOutputParser(pydantic_object=TrainingSample)

# 获取格式说明
format_instructions = parser.get_format_instructions()

# 格式说明会自动添加到系统提示词中
```

### 提示词模板

系统提示词会自动包含：

1. 用户自定义的系统提示
2. 格式说明（JSON Schema）
3. 严格要求："只输出 JSON，不要 Markdown"

示例：

```
你是一个 Java 代码分析专家。

你必须严格按照以下 JSON Schema 输出，不要添加任何额外的文字、解释或 Markdown 格式标记。
直接输出合法的 JSON 对象。

{
  "properties": {
    "scenario": { "type": "string", "enum": ["qa_rule", "arch_design"] },
    "instruction": { "type": "string" },
    "context": { "type": "string" },
    ...
  }
}
```

### 输出清理

自动清理 LLM 输出中的 Markdown 代码块标记：

```python
# 原始输出
```json
{"scenario": "qa_rule", ...}
```

# 清理后
{"scenario": "qa_rule", ...}
```

## 错误处理

### 重试机制

```python
尝试 1: 使用原始提示词
  ↓ 失败
尝试 2: 强化提示（强调只输出 JSON）
  ↓ 失败
尝试 3: 再次强化提示
  ↓ 失败
记录到 rejected_llm.jsonl + 抛出异常
```

### 拒绝样本格式

记录到 `data/intermediate/rejected_llm.jsonl` 的 JSONL 格式：

```json
{
  "timestamp": "2026-01-03T10:30:00Z",
  "system_prompt": "...",
  "user_prompt": "...",
  "raw_output": "模型的原始输出",
  "error": "ValidationError: ...",
  "model": "qwen2.5-coder-3b-instruct",
  "temperature": 0.7
}
```

### 异常类型

- `ValidationError`: Pydantic 验证失败（缺少必填字段、类型错误等）
- `ValueError`: JSON 解析失败或其他值错误
- `json.JSONDecodeError`: JSON 格式错误
- `TimeoutError`: 请求超时

## 配置优先级

配置参数的优先级（从高到低）：

1. **构造函数参数**（直接传入）
2. **环境变量**（`OLLAMA_BASE_URL` 等）
3. **配置文件**（`configs/pipeline.yaml`）
4. **默认值**（代码中的硬编码默认值）

### 示例

```python
# 配置文件: model = "qwen2.5:latest"
# 环境变量: OLLAMA_MODEL = "qwen2.5-coder-3b-instruct"
# 构造函数: model = "custom-model"

client = LLMClient(model="custom-model")
# 实际使用: custom-model

client = LLMClient()
# 实际使用: qwen2.5-coder-3b-instruct（环境变量）
```

## 性能优化

### 超时设置

根据模型大小调整超时时间：

- 小模型（3B）: 30-60 秒
- 中模型（7B）: 60-120 秒
- 大模型（14B+）: 120-300 秒

```python
client = LLMClient(timeout=120)  # 2 分钟超时
```

### 批量生成

使用循环生成多个样本时，建议添加进度条：

```python
from tqdm import tqdm

samples = []
for item in tqdm(items, desc="生成样本"):
    try:
        sample = client.generate_training_sample(...)
        samples.append(sample)
    except ValueError as e:
        logger.warning(f"Sample generation failed: {e}")
        continue
```

### 缓存和去重

考虑缓存已生成的样本，避免重复生成：

```python
import hashlib

def get_prompt_hash(system_prompt, user_prompt):
    content = f"{system_prompt}|{user_prompt}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]

# 缓存字典
cache = {}

prompt_hash = get_prompt_hash(system_prompt, user_prompt)
if prompt_hash in cache:
    sample = cache[prompt_hash]
else:
    sample = client.generate_training_sample(...)
    cache[prompt_hash] = sample
```

## 测试

### 运行自测代码

```bash
# 方式 1：直接运行模块
python -m src.engine.llm_client

# 方式 2：使用独立测试脚本
python test_llm_client.py
```

### 单元测试（待实现）

```python
import pytest
from src.engine import LLMClient

def test_llm_client_init():
    client = LLMClient()
    assert client.base_url is not None
    assert client.model is not None

def test_connection():
    client = LLMClient()
    assert client.test_connection() == True

def test_generate_sample():
    client = LLMClient()
    sample = client.generate_training_sample(
        system_prompt="Test",
        user_prompt="Test",
        scenario="qa_rule",
        repo_commit="test"
    )
    assert sample.scenario == "qa_rule"
```

## 故障排查

### 问题 1：连接失败

**症状：** `test_connection()` 返回 False

**解决：**
1. 检查 Ollama 是否运行：`ollama serve`
2. 检查端口：`curl http://localhost:11434/v1/models`
3. 检查防火墙设置

### 问题 2：模型未找到

**症状：** 错误信息包含 "model not found"

**解决：**
```bash
ollama pull qwen2.5-coder-3b-instruct
ollama list  # 验证模型已下载
```

### 问题 3：输出格式错误

**症状：** 所有重试都失败，记录到 `rejected_llm.jsonl`

**解决：**
1. 查看 `rejected_llm.jsonl` 中的 `raw_output` 字段
2. 检查模型是否理解提示词
3. 尝试降低 temperature（0.3-0.5）
4. 尝试更简单的提示词
5. 考虑切换到更大的模型

### 问题 4：生成速度慢

**症状：** 每个样本生成需要很长时间

**解决：**
1. 使用更小的模型（如 3B 而非 7B）
2. 减少 `max_tokens` 参数
3. 检查系统资源（CPU/GPU/内存）
4. 考虑使用 GPU 加速

### 问题 5：内存不足

**症状：** Ollama 崩溃或系统卡顿

**解决：**
1. 使用更小的模型
2. 减少并发生成任务
3. 增加系统交换空间
4. 使用量化模型（如 Q4_K_M）

## 最佳实践

1. **提示词设计**
   - 明确指定输出格式（JSON）
   - 提供具体示例
   - 避免模糊的指令

2. **错误处理**
   - 始终使用 try-except 捕获异常
   - 记录详细的错误信息
   - 定期检查 `rejected_llm.jsonl`

3. **性能监控**
   - 记录生成时间
   - 统计成功率
   - 分析失败原因

4. **质量控制**
   - 验证生成的样本质量
   - 人工抽查部分样本
   - 建立质量评估指标

## 相关文档

- [TrainingSample Schema](../src/utils/schemas.py)
- [配置文件说明](../configs/pipeline.yaml)
- [项目结构](../STRUCTURE.md)
- [快速参考](../QUICKREF.md)
