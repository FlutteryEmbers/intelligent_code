# 快速修复：LLM 返回空代码块问题

## 问题描述

测试 LLM Client 时出现错误：
```
✗ 生成失败: Failed to generate valid training sample after 3 attempts: 
Invalid json output: java
```

查看 `rejected_llm.jsonl` 发现模型返回了：
```
"raw_output": "```java\n\n```"
```

---

## 根本原因

`qwen2.5-coder-3b-instruct` 是一个**代码生成专用模型**，它：
- 专门为代码补全和生成优化
- 参数量小（3B），理解复杂指令能力有限
- 倾向于生成代码而非 JSON 格式的数据

---

## 立即解决（3 个步骤）

### 步骤 1：拉取推荐模型

```bash
ollama pull qwen2.5:7b
```

### 步骤 2：设置环境变量

**Windows PowerShell:**
```powershell
$env:OLLAMA_MODEL = "qwen2.5:7b"
```

**Windows CMD:**
```cmd
set OLLAMA_MODEL=qwen2.5:7b
```

**Linux/Mac:**
```bash
export OLLAMA_MODEL=qwen2.5:7b
```

### 步骤 3：重新运行测试

```bash
# 使用改进的测试脚本
python test_llm_client_improved.py

# 或使用原测试脚本
python test_llm_client.py
```

---

## 已做的改进

我已经改进了 LLM Client 的以下部分：

### 1. **更强的提示词** (`src/engine/llm_client.py`)

- ✅ 添加了 JSON 示例
- ✅ 明确禁止输出代码
- ✅ 强调必须以 `{` 开始
- ✅ 重试时显示上次失败原因

### 2. **更智能的输出清理** (`_clean_json_output`)

- ✅ 处理 `\`\`\`java` 标记
- ✅ 检测空输出
- ✅ 自动查找 JSON 对象起始位置

### 3. **改进的测试脚本**

- ✅ `test_llm_client_improved.py`：使用更简洁的提示词
- ✅ 自动检测 coder 模型并给出警告
- ✅ 提供详细的故障排查建议

---

## 模型推荐

| 场景 | 推荐模型 | 命令 |
|------|---------|------|
| **最佳选择** | qwen2.5:7b | `ollama pull qwen2.5:7b` |
| 内存充足 | qwen2.5:14b | `ollama pull qwen2.5:14b` |
| 内存有限 | qwen2.5:7b-q4 | `ollama pull qwen2.5:7b-instruct-q4_K_M` |
| 替代方案 | llama3.1:8b | `ollama pull llama3.1:8b` |

---

## 验证修复

运行改进的测试脚本：

```bash
python test_llm_client_improved.py
```

预期输出：
```
[1/5] 初始化 LLMClient...
   ✓ Base URL: http://localhost:11434/v1
   ✓ Model: qwen2.5:7b

[2/5] 测试 Ollama 连接...
   ✓ 连接成功

[3/5] 准备测试提示词...
   ✓ 提示词准备完成

[4/5] 生成训练样本（可能需要 10-30 秒）...
   ✓ 样本生成成功！

[5/5] 保存测试结果...
   ✓ 样本已保存到: data/intermediate/test_llm_sample.json

✓ 所有测试通过！
```

---

## 如果仍然失败

### 检查 1：查看拒绝日志

```bash
# Windows PowerShell
Get-Content data/intermediate/rejected_llm.jsonl | Select-Object -Last 1

# Linux/Mac
tail -n 1 data/intermediate/rejected_llm.jsonl | jq .
```

### 检查 2：验证模型

```bash
ollama list
```

确保看到 `qwen2.5:7b`。

### 检查 3：测试模型响应

```bash
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:7b",
  "prompt": "输出 JSON: {\"test\": \"ok\"}",
  "stream": false
}' | jq .
```

### 检查 4：降低 Temperature

如果输出仍然不稳定，尝试：

```python
from src.engine import LLMClient

client = LLMClient(
    model="qwen2.5:7b",
    temperature=0.3  # 降低随机性
)
```

---

## 永久配置

修改 `configs/pipeline.yaml`：

```yaml
llm:
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5:7b"  # 改为通用模型
  temperature: 0.7
  max_tokens: 3000
  timeout: 90
```

---

## 相关文档

- **[MODEL_RECOMMENDATIONS.md](MODEL_RECOMMENDATIONS.md)** - 完整的模型对比和推荐
- **[LLM_CLIENT_GUIDE.md](LLM_CLIENT_GUIDE.md)** - LLM Client 使用指南
- **[README.md](../README.md)** - 项目说明

---

## 总结

**问题**：小型 coder 模型不适合生成 JSON 格式的训练样本  
**解决**：切换到通用模型（qwen2.5:7b）  
**状态**：✅ 已优化提示词和输出解析逻辑

现在重新运行 `python test_llm_client_improved.py` 应该可以成功！
