# Bug Fix: Requirement Validation Failures

## 问题描述

在运行 `auto_requirement_generator` 时，出现大量验证失败：

```
2026-01-05 00:02:20 - WARNING - Requirement UNKNOWN validation failed: 
['Missing required field: id', 'Missing required field: goal', 
'Missing required field: constraints', 'Missing required field: acceptance_criteria', 
'Missing required field: non_goals', 'Missing required field: evidence_refs']
```

## 根本原因

通过分析 `data/intermediate/llm_output_debug.txt`，发现 LLM 输出的 JSON 格式完全错误：

### 期望格式
```json
{
  "requirements": [
    {
      "id": "REQ-AUTO-001",
      "goal": "...",
      "constraints": ["..."],
      "acceptance_criteria": ["..."],
      "non_goals": ["..."],
      "evidence_refs": [
        {
          "symbol_id": "...",
          "file_path": "...",
          "start_line": 1,
          "end_line": 2,
          "source_hash": "..."
        }
      ]
    }
  ]
}
```

### 实际输出
```json
{
  "requirements": [
    {
      "id": "1",
      "description": "Implement rate limiting...",
      "file_path": "src/main/.../AuthController.java",
      "line_range": [58, 84]
    }
  ]
}
```

### 问题总结
1. ❌ 使用 `description` 代替 `goal`
2. ❌ 使用 `file_path` 和 `line_range` 代替 `evidence_refs` 结构
3. ❌ 缺少 `constraints`, `acceptance_criteria`, `non_goals` 字段
4. ❌ ID 格式不正确（应为 "REQ-AUTO-001" 而非 "1"）

## 解决方案

### 1. 增强 System Prompt
强化 LLM 对 schema 的理解，明确禁止使用错误的字段名：

```python
system_prompt = """You are a software architecture expert specialized in generating structured requirement specifications.

ABSOLUTE REQUIREMENTS (Failure to comply will result in rejection):
1. Output MUST be valid JSON only - no markdown, no explanations
2. Use EXACT field names: id, goal, constraints, acceptance_criteria, non_goals, evidence_refs
3. DO NOT use: description, file_path, line_range, code_location
4. DO NOT create nested "requirements" keys
5. Each requirement MUST contain ALL required fields
...
"""
```

### 2. 优化 Prompt 模板
在 `configs/prompts/auto_requirement_generation.txt` 开头添加：

```
## MANDATORY SCHEMA (DO NOT DEVIATE)
Your output MUST use these EXACT field names (NO substitutions allowed):
- id (NOT: requirement_id, req_id, number)
- goal (NOT: description, summary, objective, title)
- constraints (NOT: limitations, restrictions)
- acceptance_criteria (NOT: success_criteria, verification)
- non_goals (NOT: out_of_scope, exclusions)
- evidence_refs (NOT: references, code_location, file_path, line_range)
```

### 3. 添加完整示例
在 prompt 中提供一个完整的工作示例，展示正确的 JSON 结构。

### 4. Schema 验证与报错
改进 `_parse_llm_output` 方法，检测常见错误并提供详细报错：

```python
if 'description' in first_req:
    wrong_fields.append('description (should be: goal)')
if 'file_path' in first_req and 'evidence_refs' not in first_req:
    wrong_fields.append('file_path (should be inside: evidence_refs)')
```

### 5. 自动字段映射（容错机制）
添加 `_attempt_field_mapping` 方法，尝试自动修复常见错误：

- `description` → `goal`
- `file_path` + `line_range` → 构造 `evidence_refs`
- 缺失字段 → 提供合理的默认值

### 6. 增强日志记录
在验证失败时记录实际字段名，便于调试：

```python
actual_fields = list(req.keys())
logger.warning(f"Requirement {req_id} fields: {actual_fields}")
```

## 文件修改清单

### 修改的文件
1. **src/engine/auto_requirement_generator.py**
   - 增强 `_call_llm` 的 system_prompt
   - 改进 `_parse_llm_output` 的 schema 验证
   - 新增 `_attempt_field_mapping` 方法（自动修复）
   - 增强验证失败时的日志记录

2. **configs/prompts/auto_requirement_generation.txt**
   - 添加 "MANDATORY SCHEMA" 部分
   - 添加完整的工作示例
   - 强化字段名要求

## 测试建议

### 1. 验证修复效果
```bash
cd d:\Codes\intelligent_code_generator
python -m src.engine.auto_requirement_generator --symbols data/raw/extracted/symbols.jsonl
```

### 2. 检查输出
- 查看 `data/intermediate/requirements_auto.jsonl` 是否生成了有效需求
- 查看 `data/intermediate/requirements_auto_rejected.jsonl` 了解拒绝原因
- 查看 `data/intermediate/llm_output_debug.txt` 检查 LLM 原始输出

### 3. 日志分析
成功的日志应该显示：
```
INFO - Batch X: Generated Y requirements
INFO - Successfully mapped N requirements to correct schema (如果触发了自动修复)
INFO - Batch X results: parsed=Y, added=Z, total=N
```

## 预期改进

1. ✅ LLM 更容易理解和遵循正确的 schema
2. ✅ 即使 LLM 使用错误字段名，自动修复机制可以挽救部分输出
3. ✅ 更详细的错误日志帮助快速定位问题
4. ✅ 完整的工作示例降低 LLM 理解难度

## 后续优化建议

如果问题仍然存在，可以考虑：

1. **Few-shot Learning**: 在 prompt 中提供 2-3 个真实示例
2. **Temperature 调整**: 降低 temperature (如 0.3) 提高输出稳定性
3. **模型切换**: 尝试更强的模型（如 qwen2.5:14b 或 qwen2.5:32b）
4. **分步生成**: 先生成简单字段，再生成复杂的 evidence_refs
5. **JSON Schema Validation**: 在 prompt 中嵌入 JSON Schema 定义

## 相关文件

- 代码: [src/engine/auto_requirement_generator.py](../src/engine/auto_requirement_generator.py)
- Prompt: [configs/prompts/auto_requirement_generation.txt](../configs/prompts/auto_requirement_generation.txt)
- 配置: [configs/pipeline.yaml](../configs/pipeline.yaml)
- Schema: [src/utils/schemas.py](../src/utils/schemas.py)
