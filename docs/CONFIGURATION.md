# 配置与运维手册

## ⚙️ 仪表盘配置

主要配置文件通常位于 `configs/launch.yaml`。下表列出了常用的调节参数及其作用。

| 配置参数 | 业务名称 | 调节它的效果 | 专家建议 |
| :--- | :--- | :--- | :--- |
| `repo.path` | 代码仓路径 | 指定解析对象 | 指向目标仓库 |
| `language.name` | 语言类型 | 选择解析器 | java / python |
| `llm.model` | 生成模型 | 控制生成质量与成本 | `qwen2.5:7b` |
| `method_understanding.enabled` | 方法理解开关 | 是否产出方法画像 | demo 开启 |
| `question_answer.max_questions` | QA 问题上限 | 控制问答规模 | 25 |
| `design_questions.max_questions` | 设计问题上限 | 控制设计样本规模 | 30 |
| `quality.gate_mode` | 质量门禁 | gate / report | demo 可 report |
| `question_answer.coverage.targets` | QA 难度分布 | 高/中/难比例 | 0.8/0.15/0.05 |
| `safety.mode` | 敏感信息处理 | drop / sanitize / keep | demo 可 keep |
| `dedup.semantic.enabled` | 语义去重开关 | 是否开启语义去重 | demo 可关闭 |

## 环境变量

除了 `.yaml` 配置文件，系统也支持使用环境变量进行覆盖配置。

### Windows
```bash
set REPO_PATH=D:\path\to\repo
set OLLAMA_BASE_URL=http://localhost:11434
set OLLAMA_MODEL=qwen2.5:7b
```

### Linux/Mac
```bash
export REPO_PATH=/path/to/repo
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b
```

## CLI 常用参数

运行 `python main.py` 时可用的参数：

- `--config`：指定配置文件（默认 `configs/launch.yaml`）
- `--skip-parse`：跳过解析
- `--skip-question-answer`：关闭 Auto QA（使用用户问题）
- `--skip-auto-design-questions`：跳过自动设计问题生成
- `--skip-llm`：跳过所有 LLM 生成
- `--skip-qa`：跳过 QA 生成
- `--skip-design`：跳过设计生成
- `--skip-dedup`：跳过去重
- `--skip-safety`：跳过安全扫描
- `--skip-export`：跳过导出

示例：
```bash
# 指定配置文件
python3 main.py --config configs/launch.yaml

# 快速跳过耗时步骤
python3 main.py --skip-parse --skip-llm --skip-export
```

## 📐 样本数量计算逻辑

### QA 样本数量决定链

```
1. MethodUnderstanding
   ├── 输入: symbols.jsonl 中的所有方法符号
   └── 输出: method_profiles.jsonl
       └── 数量限制: max_methods (默认 25)

2. AutoQuestionGenerator
   ├── 输入: method_profiles (最多 25 个)
   ├── 每个 profile 生成问题数: questions_per_method (默认 3)
   ├── 潜在问题数 = 25 × 3 = 75 个
   └── 输出限制: max_questions (默认 15)
       └── 实际输出: min(75, 15) = 15 个问题

3. AnswerGenerator
   ├── 输入: 15 个问题
   └── 输出: 每个问题生成 1 个答案 → 15 个 QA 样本
       └── 质量门禁后: 15 - rejected = 最终 QA 数
```

| 配置项 | 路径 | 默认值 | 作用 |
|--------|------|--------|------|
| `max_methods` | `method_understanding.max_methods` | 25 | 限制处理的方法数 |
| `questions_per_method` | `question_answer.questions_per_method` | 3 | 每个方法生成多少问题 |
| `max_questions` | `question_answer.max_questions` | 15 | QA 问题总数上限 |

**公式**:
```
最终 QA 数 = min(max_methods × questions_per_method, max_questions) - rejected
           = min(25 × 3, 15) - rejected
           = 15 - rejected
```

### Design 样本数量决定链

```
1. DesignQuestionGenerator
   ├── 输入: symbols.jsonl + method_profiles.jsonl (可选)
   └── 输出: design_questions_auto.jsonl
   └── 数量限制: max_questions (默认 10)

2. DesignGenerator
   ├── 输入: 10 个设计问题
   ├── 每个问题生成 1 个设计样本
   └── 内部上限: max_samples (默认 50)
       └── 实际受限于设计问题数，通常是 10

3. 输出: 10 个 Design 样本
   └── 质量门禁后: 10 - rejected = 最终 Design 数
```

| 配置项 | 路径 | 默认值 | 作用 |
|--------|------|--------|------|
| `max_questions` | `design_questions.max_questions` | 10 | 设计问题总数上限 |
| `max_samples` | `core.max_items` | 50 | Design 样本内部上限 |
| `use_method_profiles` | `design_questions.use_method_profiles` | true | 是否用 profiles 增强 |

**公式**:
```
最终 Design 数 = min(design_questions_count, max_samples) - rejected
              = min(10, 50) - rejected
              = 10 - rejected
```

**关键结论**:
1. **QA 瓶颈在 `max_questions`**
2. **Design 瓶颈在 `design_questions.max_questions`**
3. **Rejected 样本不影响生成数量计算** (它们是生成后被过滤的)
