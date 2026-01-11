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

## 🎭 Prompt 管理指南

系统采用 **“结构化骨架 + 语言 Profile”** 的混合管理模式，以实现多语言支持的逻辑复用。

### 1. 目录结构

所有 Prompt 模板位于 `configs/prompts/` 目录下：

- `common/`: 存放跨场景通用的 JSON 规则、架构约束等。
- `qa_rule/`: 问答对生成相关的 system 和 user 模板。
- `arch_design/`: 架构设计方案生成相关的模板。
- `method_profile/`: 方法摘要理解相关的模板。

### 2. 骨架模板 (Skeletons)

模板中使用 `{placeholder}` 语法进行动态注入，核心占位符包括：

- `{role_identity}`: 从 `configs/language/*.yaml` 中抽取的角色定义。
- `{language}`: 目标编程语言名称。
- `{common_json_rules}`: 从 `configs/prompts/common/json_rules.txt` 加载的通用格式约束。

### 3. 多语言支持 (Language Profiles)

在 `configs/language/java.yaml` 或 `python.yaml` 中定义了场景特定的角色描述：

```yaml
roles:
  qa_rule_role: "你是一个资深的 Java 业务分析师..."
  arch_design_role: "你是一个精通 Spring 生态的架构师..."
  method_profile_role: "你是一个 Java 代码审计专家..."
```

系统会根据 `launch.yaml` 中的 `language.name` 自动加载对应的 Profile。

## 📐 样本数量计算逻辑

...

### QA 样本数量决定链

```
1. MethodUnderstanding
   ├── 输入: symbols.jsonl 中的所有方法符号
   └── 输出: method_profiles.jsonl
       └── 数量限制: max_methods (默认 25)

2. QuestionGenerator
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
   ├── 输入: symbols.jsonl（method_profiles 仅用于 embeddings 构建）
   └── 输出: design_questions_auto.jsonl
   └── 数量限制: min(max_questions, max_samples) (默认 10)

2. DesignGenerator
   ├── 输入: 10 个设计问题
   ├── 每个问题生成 1 个设计样本
   └── 内部上限: min(max_questions, max_samples) (默认 10)
       └── 实际受限于两者的最小值

3. 输出: 10 个 Design 样本
   └── 质量门禁后: 10 - rejected = 最终 Design 数
```

| 配置项 | 路径 | 默认值 | 作用 |
|--------|------|--------|------|
| `max_questions` | `design_questions.max_questions` | 10 | 设计问题总数上限 |
| `max_samples` | `design_questions.max_samples` | 50 | Design 样本内部上限 |
| `use_method_profiles` | `design_questions.use_method_profiles` | true | 是否生成 profiles 供 embeddings 使用 |

**公式**:

```
最终 Design 数 = min(design_questions_count, max_questions, max_samples) - rejected
              = min(10, 10, 50) - rejected
              = 10 - rejected
```

**关键结论**:

1. **QA 瓶颈在 `max_questions`**
2. **Design 瓶颈在 `min(design_questions.max_questions, design_questions.max_samples)`**
3. **Rejected 样本不影响生成数量计算** (它们是生成后被过滤的)
