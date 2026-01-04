# LLM 模型推荐与故障排查

## 问题：模型返回空的代码块

如果你遇到类似错误：
```
✗ 生成失败: Invalid json output: java
raw_output: "```java\n\n```"
```

这表示模型返回了空的 Java 代码块而不是 JSON。

---

## 原因分析

`qwen2.5-coder-3b-instruct` 是一个**代码生成模型**，专门针对代码补全和生成任务优化。它可能：
1. 更倾向于生成代码而非 JSON
2. 参数量较小（3B），理解复杂指令的能力有限
3. 对"生成训练样本"这类元任务理解不够好

---

## 解决方案

### 方案 1：切换到通用模型（推荐）

使用更大的通用模型，而非 coder 专用模型：

```bash
# 推荐：Qwen 2.5 通用模型（7B）
ollama pull qwen2.5:7b
export OLLAMA_MODEL=qwen2.5:7b

# 或使用 14B 版本（更好，但需要更多内存）
ollama pull qwen2.5:14b
export OLLAMA_MODEL=qwen2.5:14b

# 或使用 Llama 3.1
ollama pull llama3.1:8b
export OLLAMA_MODEL=llama3.1:8b
```

然后重新运行测试：
```bash
python test_llm_client_improved.py
```

### 方案 2：使用量化版本（节省内存）

如果内存有限，使用量化版本：

```bash
# Q4 量化（推荐，性能和内存平衡）
ollama pull qwen2.5:7b-instruct-q4_K_M
export OLLAMA_MODEL=qwen2.5:7b-instruct-q4_K_M

# Q8 量化（更好的质量）
ollama pull qwen2.5:7b-instruct-q8_0
export OLLAMA_MODEL=qwen2.5:7b-instruct-q8_0
```

### 方案 3：调整配置文件

永久修改配置文件 `configs/pipeline.yaml`：

```yaml
llm:
  model: "qwen2.5:7b"  # 改为通用模型
  temperature: 0.5     # 降低温度提高一致性
  max_tokens: 3000     # 增加 token 限制
```

### 方案 4：降低 Temperature

如果必须使用 coder 模型，尝试降低 temperature：

```python
client = LLMClient(
    model="qwen2.5-coder-3b-instruct",
    temperature=0.3  # 降低随机性
)
```

---

## 模型对比

| 模型 | 参数量 | 用途 | 推荐度 | 内存需求 |
|------|--------|------|--------|----------|
| `qwen2.5-coder-3b-instruct` | 3B | 代码生成 | ⭐⭐ | ~2GB |
| `qwen2.5:7b` | 7B | 通用 | ⭐⭐⭐⭐⭐ | ~4GB |
| `qwen2.5:14b` | 14B | 通用 | ⭐⭐⭐⭐⭐ | ~8GB |
| `llama3.1:8b` | 8B | 通用 | ⭐⭐⭐⭐ | ~5GB |
| `qwen2.5:7b-instruct-q4_K_M` | 7B (Q4) | 通用 | ⭐⭐⭐⭐ | ~3GB |

---

## 测试步骤

### 1. 检查当前模型

```bash
ollama list
```

### 2. 拉取推荐模型

```bash
ollama pull qwen2.5:7b
```

### 3. 设置环境变量

```bash
# Windows PowerShell
$env:OLLAMA_MODEL = "qwen2.5:7b"

# Windows CMD
set OLLAMA_MODEL=qwen2.5:7b

# Linux/Mac
export OLLAMA_MODEL=qwen2.5:7b
```

### 4. 运行改进的测试脚本

```bash
python test_llm_client_improved.py
```

---

## 验证模型是否可用

```bash
# 测试模型
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b",
  "prompt": "输出 JSON: {\"test\": \"ok\"}",
  "stream": false
}'

# 列出所有模型
curl http://localhost:11434/api/tags
```

---

## 常见错误解决

### 错误 1：模型未找到

```
Error: model 'qwen2.5:7b' not found
```

**解决**：
```bash
ollama pull qwen2.5:7b
```

### 错误 2：内存不足

```
Error: failed to load model: insufficient memory
```

**解决**：
1. 使用更小的模型或量化版本
2. 关闭其他占用内存的程序
3. 增加系统交换空间

### 错误 3：连接超时

```
TimeoutError: Request timed out
```

**解决**：
```python
client = LLMClient(timeout=120)  # 增加到 2 分钟
```

---

## 性能对比（参考）

| 操作 | 3B Coder | 7B 通用 | 14B 通用 |
|------|----------|---------|----------|
| 生成速度 | 最快 | 中等 | 较慢 |
| 输出质量 | 一般 | 好 | 很好 |
| 成功率 | ~30% | ~80% | ~95% |
| 适合任务 | 代码补全 | 通用生成 | 复杂推理 |

---

## 最佳实践

1. **生产环境**：使用 `qwen2.5:7b` 或更大
2. **开发测试**：可以使用 `qwen2.5-coder-3b-instruct` 快速迭代
3. **内存有限**：使用 Q4 量化版本
4. **质量优先**：使用 14B 或更大的模型

---

## 下一步

如果切换模型后仍然失败，请：
1. 检查 `data/intermediate/rejected_llm.jsonl` 查看具体错误
2. 查看日志文件 `logs/pipeline.log`
3. 尝试更简单的提示词
4. 考虑调整 temperature 和 max_tokens 参数

---

**推荐配置**（适合大多数用户）：

```yaml
# configs/pipeline.yaml
llm:
  model: "qwen2.5:7b"
  temperature: 0.7
  max_tokens: 3000
  timeout: 90
```

```bash
# 环境变量
export OLLAMA_MODEL=qwen2.5:7b
export LLM_TEMPERATURE=0.7
```
