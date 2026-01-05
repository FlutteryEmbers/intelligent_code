# 第二轮修复：强化 Schema 约束

## 问题分析

即使在第一轮修复后，LLM 仍然返回错误的格式：

### Batch 1 实际输出
```json
{
  "name": "Register User",
  "description": "...",
  "expected_behavior": "...",
  "test_cases": [...]
}
```
- ❌ 使用 `name`、`description`、`expected_behavior`、`test_cases`
- ❌ 缺少 `id` 字段
- ❌ 完全是"测试用例"格式，不是"架构需求"格式

### Batch 2 实际输出
```json
{
  "id": "req_001",
  "description": "...",
  "qualified_name": "..."
}
```
- ❌ 使用 `description` 而非 `goal`
- ❌ 缺少 `constraints`、`acceptance_criteria`、`non_goals`、`evidence_refs`

## 根本问题

1. **LLM 完全没有理解我们的 schema 要求**
2. **Prompt 中的 schema 说明被忽略或理解错误**
3. **temperature 0.7 可能太高，导致输出不稳定**

## 第二轮修复措施

### 1. 将 Schema 直接嵌入 System Prompt

之前：Schema 只在 user prompt 中说明  
现在：在 system prompt 中直接展示完整的 JSON 示例

```python
system_prompt = """You are a JSON generation machine. Your ONLY task is to output valid JSON matching this EXACT schema:

{
  "requirements": [
    {
      "id": "REQ-AUTO-001",
      "goal": "string (10-25 words)",
      "constraints": ["string", "string"],
      "acceptance_criteria": ["string with metrics", "string with numbers"],
      "non_goals": ["string"],
      "evidence_refs": [
        {
          "symbol_id": "exact value from evidence pool",
          "file_path": "exact value from evidence pool",
          "start_line": 123,
          "end_line": 456,
          "source_hash": "exact value from evidence pool"
        }
      ]
    }
  ]
}

FORBIDDEN field names (will cause REJECTION):
- name, title, summary, objective → MUST USE: goal
- description → MUST USE: goal
- expected_behavior, test_cases → WRONG FORMAT
- file_path, line_range (at top level) → MUST USE: evidence_refs array
```

### 2. 在 Prompt 开头添加超强警告

在 `auto_requirement_generation.txt` 开头添加：

```
⚠️ CRITICAL: You MUST output JSON matching this EXACT schema. Any deviation will be REJECTED.

## FORBIDDEN FORMATS (These will cause IMMEDIATE REJECTION)
❌ WRONG:
{"name": "...", "description": "...", "test_cases": [...]}
{"id": "...", "description": "...", "qualified_name": "..."}
```

### 3. 降低 Temperature

```yaml
temperature: 0.2  # 从 0.7 降低到 0.2
```

更低的 temperature 会让输出更稳定、更遵循指令。

### 4. 添加详细日志

```python
logger.info(f"LLM config: model={self.llm_client.model}, temperature={self.llm_client.temperature}, "
           f"max_tokens={self.llm_client.max_tokens}")
```

### 5. 输出前的 Checklist

在 prompt 最后添加：

```
DOUBLE-CHECK before outputting:
- [ ] Using "goal" field (not "description" or "name")
- [ ] Using "evidence_refs" array (not "file_path" or "line_range")
- [ ] All 6 required fields present
- [ ] evidence_refs has at least 2 items
- [ ] acceptance_criteria contains numbers/metrics
```

## 测试步骤

### 1. 测试 LLM 基础能力

运行简化测试：

```bash
python test_llm_schema.py
```

这会发送一个非常简单的请求给 LLM，检查它是否能生成正确的 JSON schema。

**预期输出**：
- ✅ JSON 可以被解析
- ✅ 包含所有 6 个必需字段
- ✅ 使用正确的字段名（goal 而非 description）

**如果失败**：说明 LLM 模型本身可能不适合这个任务，需要：
- 换用更强的模型（如 qwen2.5:14b 或 qwen2.5:32b）
- 或者考虑使用 few-shot learning（提供 2-3 个完整示例）

### 2. 运行完整测试

如果步骤 1 成功：

```bash
python -m src.engine.auto_requirement_generator --symbols data/raw/extracted/symbols.jsonl
```

**观察日志**：
- LLM 配置是否显示 `temperature=0.2`
- 是否仍然出现 "WRONG field names" 警告
- `Field mapping: X input -> Y fixed` 中 Y 是否 > 0

### 3. 检查输出文件

```bash
# 查看成功生成的需求
cat data/intermediate/requirements_auto.jsonl

# 查看被拒绝的需求
cat data/intermediate/requirements_auto_rejected.jsonl

# 查看 LLM 原始输出（调试用）
cat data/intermediate/llm_output_debug.txt
```

## 预期结果

### 成功标志

```
INFO - Batch 1: LLM returned X characters
INFO - Field mapping: 2 input -> 2 fixed  # 或者直接解析成功，不需要 mapping
INFO - Batch 1 results: parsed=2, added=2, total=2
INFO - Batch 2: LLM returned Y characters
...
INFO - Generated requirements: 6
INFO - Rejected requirements: 0
```

### 如果仍然失败

考虑以下进一步措施：

#### A. 切换到更强的模型

```yaml
# configs/pipeline.yaml
llm:
  model: "qwen2.5:14b"  # 或 qwen2.5:32b
  temperature: 0.2
```

#### B. 使用 Few-shot Learning

在 prompt 中提供 2-3 个完整的真实示例（不是模板，是真实的 requirement）。

#### C. 分步生成

不要一次生成完整的 requirement，而是：
1. 先生成 id 和 goal
2. 再生成 constraints 和 acceptance_criteria
3. 最后生成 evidence_refs

#### D. JSON Schema 验证

在 prompt 中嵌入完整的 JSON Schema 定义，让 LLM 更精确地理解结构。

#### E. 使用 Function Calling

如果 LLM 支持 OpenAI 的 function calling API，可以定义 function schema 来强制输出格式。

## 修改的文件

1. [src/engine/auto_requirement_generator.py](../src/engine/auto_requirement_generator.py)
   - 强化 system_prompt
   - 添加 LLM 配置日志

2. [configs/prompts/auto_requirement_generation.txt](../configs/prompts/auto_requirement_generation.txt)
   - 开头添加超强警告和负面示例
   - 输出部分添加 checklist

3. [configs/pipeline.yaml](../configs/pipeline.yaml)
   - temperature: 0.7 → 0.2

4. [test_llm_schema.py](../test_llm_schema.py) (新增)
   - 简化测试脚本，验证 LLM 基础能力

## 下一步

1. 运行 `python test_llm_schema.py` 验证 LLM 基础能力
2. 根据测试结果决定是否需要切换模型或采用 few-shot learning
3. 运行完整的 requirement generation
4. 分析结果并继续优化

## 参考资料

- [第一轮修复文档](BUGFIX_REQUIREMENT_VALIDATION.md)
- [Pipeline 架构文档](PIPELINE_ARCHITECTURE.md)
- [Qwen2.5 模型文档](https://github.com/QwenLM/Qwen2.5)
