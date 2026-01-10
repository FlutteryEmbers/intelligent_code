# Refactoring & Debugging Summary - 2026-01-10

以下是本次重构过程中遇到的关键 Bug 及其根本原因总结：

### 1. 路径转义导致 JSON 解析失败 (`Invalid \escape`)

* **现象**: `MethodUnderstander` 报错，提示 `JSONDecodeError: Invalid \escape`。
* **原因**: Windows 系统的文件路径包含反斜杠 `\` (例如 `Backend\views.py`)。当这些路径直接注入到 Prompt 的 JSON 字符串中时（例如 `"file_path": "Backend\views.py"`），`\v` 等组合被视为非法转义字符，导致 JSON 格式错误。
* **修复**: 在所有生成器中引入 `normalize_path_separators`，将路径统一转换为正斜杠 `/` (`Backend/views.py`)。

### 2. 符号 ID 不匹配 (`EVIDENCE_SYMBOL_NOT_FOUND`)

* **现象**: Pipeline 验证步骤大量拒绝 QA 样本，提示 "Symbol not found"。
* **原因**: LLM 在复制 `symbol_id` 时，有时会调整行号后缀（例如将 `...:11` 改为 `...:12`），导致生成的 ID 与系统记录的原始 ID 字符串不完全匹配。验证器要求精确匹配，因此报错。
* **修复**: 在 `AnswerGenerator` 和 `DesignGenerator` 中增加 `_correct_evidence_refs` 逻辑，支持忽略行号后缀的“模糊匹配”，并用系统原始 ID 覆盖 LLM 的输出。

### 3. DesignGenerator 校验失败 (`ValidationError: start_line >= 1`)

* **现象**: 设计样本全部生成失败，导致后续 Merge 步骤因缺少文件而中断。
* **原因**: 在 Prompt 中注入的“现有代码架构”和“相关组件证据”中，**缺少了 line_number 信息**。LLM 无法获知代码的具体行号，因此输出 `0` 或空值，导致不满足 `EvidenceRef` Schema 中 `start_line >= 1` 的约束。
* **修复**: 更新 Prompt 注入逻辑，显式包含 start/end line 信息。

### 4. 代码与配置不一致 (`KeyError` / `TypeError`)

* **KeyError 'common_mistakes_examples'**: `AnswerGenerator` 代码尝试填充 prompt 模板中的占位符，但代码逻辑中缺少了该参数的传递。
* **TypeError 'language'**: `DesignQuestionGenerator` 手动传递了 `language` 参数，而基类 `BaseGenerator` 也自动注入了该参数，导致参数冲突。
* **AttributeError 'list' object...**: 系统读取 `python.yaml` 配置时，代码对 `common_mistakes` 结构的防御性编程不足（未能正确处理可能的类型异常），导致解析错误。

### 总结

这些问题主要集中在 **Windows 路径兼容性**、**LLM 输出的精确性控制** 以及 **Prompt 上下文信息的完整性** 上。通过统一路径规范、增加 ID 模糊匹配纠错机制以及补全 Prompt 上下文，上述问题已得到解决。
