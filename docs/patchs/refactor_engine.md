# Implementation Plan - Refactoring `src/engine`

针对 `src/engine` 模块提出重构方案，目标是实现**Prompt 零硬编码**、**逻辑职责分层**以及**多语言高度复用**。

## 现状分析 (Current State)

### 1. 硬编码与多语言不一致

- 代码中硬编码了 "资深 Java 架构师" 等限定词。
- `configs/language/java.yaml` 和 `python.yaml` 中虽有部分 Prompt 储备，但未 with `engine` 生成逻辑打通。
- `configs/prompts/` 目录下的模板与各生成器类的内部字符串存在逻辑重合。

## 重构目标 (Goals)

1. **Hybrid Prompt Management**：
    - **结构模板** (Structural Templates) 存放在 `configs/prompts/`。
    - **语言特性** (Language Traits) 存放在 `configs/language/`。
2. **基类驱动**：通过 `BaseGenerator` 自动寻找并组装“模板 + 语言补丁”。
3. **RAG 算法下沉**：将检索与排序逻辑从业务类中剥离到 `src/engine/rag/`。

---

## 详细：硬编码消除逻辑 (Hardcoding Removal Logic)

我们将引入 `BaseGenerator` 作为所有生成器的父类，核心逻辑如下：

### 1. 结构化 Prompt 组装

不再在各子类中定义 `system_prompt = "..."`，而是调用 `self._build_composed_prompt(scenario_type)`。

```python
# BaseGenerator 内部伪代码
def _build_composed_prompt(self, scenario: str, prompt_type: str = "system"):
    # 1. 加载语言配置 (Trait)
    lang_cfg = self.language_profile # 加载自 configs/language/{lang}.yaml
    role_identity = lang_cfg.get(f"system_prompts.{scenario}_role") 
    
    # 2. 加载场景模板 (Skeleton)
    template = self._load_template(f"{scenario}/{prompt_type}.txt")
    
    # 3. 加载规则 (Rules/Constraints)
    # 例如 negative_rules 从 configs/prompts/qa_rule/negative_rules.yaml 加载
    
    # 动态渲染
    return template.format(
        role_identity=role_identity,
        language=self.language_name,
        # ... 其他变量
    )
```

### 2. 硬编码迁移对照表

| 原始硬编码位置 | 原始形式 (Before) | 重构后形式 (After) | 存储位置 |
| :--- | :--- | :--- | :--- |
| **System Role** | `f"你是一位资深的 {lang} 架构师..."` | `{role_identity}` 变量 | `configs/language/{lang}.yaml` (Key: `{scenario}_role`) |
| **Negative Rules** | `rules_map = {"wrong_premise": [...]}` | `self.prompt_manager.get_rule(type)` | `configs/prompts/qa_rule/negative_rules.yaml` |
| **Format Constraints** | `format_constraints = "## JSON 格式..."` | `lang_cfg.answer_gen.format_constraints` | `configs/language/{lang}.yaml` |
| **Clean Logic** | 各自实现 `_clean_json_output` | 调用 `BaseGenerator._clean_and_parse_json` | `src/engine/core/base_generator.py` |

### 3. 配置化负向规则 (YAML 示例)

新建 `configs/prompts/qa_rule/negative_rules.yaml`:

```yaml
insufficient_evidence:
  title: "证据不足"
  rules:
    - "明确说明证据不足，无法给出完整结论。"
    - "指出需要补充的具体代码位置。"
wrong_premise:
  title: "前提错误"
  rules:
    - "先指出问题前提不成立，再给出正确前提。"
```

### 4. 存量 Prompt 骨架化 (Skeleton Refactoring)

为了确保风格统一并实现真正的多语言复用，我们需要对 `configs/prompts/` 下的存量文件进行“脱敏”处理：

- **Before**: `你是一位资深的 Java 架构师... 分析 Java 代码...` (硬编码)
- **After**: `{role_identity}... 分析 {language} 代码...` (占位符)

**操作清单：**

1. **清理系统提示词**：将 `qa_system_prompt.txt` 等文件中的语言限定词替换为占位符。
2. **提取共性**：如果多个文本文件在“输出格式要求”上高度一致，则将其提取为 `common_json_rules.txt`，由 `BaseGenerator` 动态包含。
3. **语言档案补齐**：将原本散留在 Prompt 里的 Java/Python 特性描述（如 Javadoc vs Docstring 的称呼）移入 `configs/language/*.yaml`。

### 5. Prompt 文件重命名对照表

为了使文件系统与 `src/schemas/` 中的 `scenario` 定义保持一致，建议对 `configs/prompts/` 目录进行重新组织：

| 原始路径 (Old Path) | 新路径 (New Path) | 对应 Scenario (Schema) | 备注 |
| :--- | :--- | :--- | :--- |
| `question_answer/qa_system_prompt.txt` | `qa_rule/system.txt` | `qa_rule` | 问答场景系统骨架 |
| `question_answer/auto_answer_generation.txt` | `qa_rule/gen_a_user.txt` | `qa_rule` | 自动回答 User 模板 |
| `question_answer/auto_question_generation.txt` | `qa_rule/gen_q_user.txt` | `qa_rule` | 自动出题 User 模板 |
| (硬编码) | `qa_rule/negative_rules.yaml` | `qa_rule` | 配置化负向规则库 |
| `design/design_system_prompt.txt` | `arch_design/system.txt` | `arch_design` | 架构设计系统骨架 |
| `design/design_user_prompt.txt` | `arch_design/gen_s_user.txt` | `arch_design` | 方案生成 User 模板 (Solution) |
| `design/auto_design_question_generation.txt` | `arch_design/gen_q_user.txt` | `arch_design` | 设计问题生成 User 模板 |
| (硬编码) | `method_profile/system.txt` | `method_profile` | 方法画像提取系统骨架 |
| `method_understanding/auto_method_understanding.txt` | `method_profile/user.txt` | `method_profile` | 方法特征提取 User 模板 |
| (新文件) | `common/json_rules.txt` | (Shared) | 通用 JSON 格式约束骨架 |
| (硬编码) | `test/connection_test_system.txt` | (Internal Test) | LLM 连接测试专用 |

### 6. User Inputs 中的 Prompt 逻辑迁移

`configs/user_inputs/` 下的部分文件本质上是 Prompt 的组成部分（场景约束和全局规则），也应纳入提示词管理体系：

| 原始路径 (Old Path) | 新路径 (New Path) | 对应 Scenario (Schema) | 备注 |
| :--- | :--- | :--- | :--- |
| `user_inputs/qa_scenario_templates.yaml` | `qa_rule/scenario_rules.yaml` | `qa_rule` | 场景注入规则 (Fuzzy, ambiguous etc.) |
| `user_inputs/design_scenario_templates.yaml` | `arch_design/scenario_rules.yaml` | `arch_design` | 设计场景注入规则 |
| `user_inputs/architecture_constraints.yaml` | `common/arch_constraints.yaml` | 全局架构约束 | 生成方案时的通用准则 |

> [!NOTE]
> `design_questions.yaml` 和 `user_questions.yaml` 属于**种子数据 (Seed Data)**，不属于 Prompt 模板，保留在 `configs/user_inputs/` 下。

---

### 7. Engine 模块重构重命名对照表

我们将 `src/engine/` 下的大类和单文件拆分为功能更明确的子包和子模块：

| 原始文件 (Old File) | 新路径 (New Path) | 核心职责 | 备注 |
| :--- | :--- | :--- | :--- |
| `llm_client.py` | `core/llm_client.py` | LLM 基本调用与封装 | 移入核心包 |
| (新文件) | `core/base_generator.py` | 提供提示词加载、批处理逻辑基类 | 核心基类 |
| (提取自各 Generator) | `rag/retriever.py` | 上下文搜索、关键词打分、层级平衡 | RAG 专用模块 |
| `auto_question_generator.py` | `generators/qa_rule/question_generator.py` | QA 场景：自动出题逻辑 | 对齐 `qa_rule` schema |
| `answer_generator.py` | `generators/qa_rule/answer_generator.py` | QA 场景：自动回答逻辑 | 对齐 `qa_rule` schema |
| `auto_design_question_generator.py` | `generators/arch_design/question_generator.py` | 架构场景：设计问题生成 | 对齐 `arch_design` schema |
| `design_generator.py` | `generators/arch_design/design_generator.py` | 架构场景：方案实现生成 | 对齐 `arch_design` schema |
| `auto_method_understander.py` | `generators/method_profile/understander.py` | 基础能力：方法级特征提取 | 对齐 `method_profile` schema |

---

## 建议重构思路 (Proposed Approach)

### 1. 结构化分包 `src/engine/`

- `src/engine/core/`：
  - `base_generator.py`：实现模板加载器 `_load_template(name)`。
- `src/engine/rag/`：抽取通用的关键词权重计算。
- `src/engine/generators/`：
  - `qa_rule/`, `arch_design/`, `method_profile/`：子包命名与 `src/schemas/` 严格一致。

### 2. 执行步骤 (Steps)

详细步骤请参阅本文第 10 节 **“详细执行步骤与依赖关系”**。

---

### 7. 通用方法分组与 Utilities 联动

为了最大化复用 `src/utils` 下的已有工具，我们将 `BaseGenerator` 中的方法划分为以下四个核心组：

#### 1. 配置与生命周期组 (Config & Lifecycle)

- **职责**：初始化环境、解析路径、管理批处理状态。
- **联动 Utils**：
  - 调用 `src.utils.generation.config_helpers` 解析覆盖率、检索和路径配置。
  - 调用 `create_seeded_rng` 确保采样可复现。
- **核心方法**：`__init__`, `_ensure_outputs`, `_load_resume_state` (存量逻辑收敛)。

#### 2. 提示词工程组 (Prompt Engineering)

- **职责**：执行“骨架 + 语言补丁”的动态拼装，注入负向规则。
- **联动 Utils**：
  - 使用 `src.utils.io.file_ops.load_prompt_template`。
  - 使用 `src.utils.generation.language_profile` 获取语言特性。
- **核心方法**：`_build_composed_system_prompt`, `_build_composed_user_prompt`, `_inject_negative_rules` (从逻辑硬编码转为配置化加载)。

#### 3. 执行与重试组 (Execution & Retry)

- **职责**：封装 LLM 调用，提供统一的清洗、解析和重试逻辑。
- **联动 Utils**：
  - 使用 `src.utils.io.file_ops.clean_llm_json_output`。
- **核心方法**：`call_llm_with_retry`, `_clean_and_parse_json`, `_log_rejected` (格式化记录拒绝原因)。

#### 4. 检索委托组 (Retrieval Delegation)

- **职责**：将具体的 RAG 过程委托给 RAG 模块。
- **联动 Utils**：
  - 使用 `src.utils.retrieval.call_chain` 进行调用链扩展。
- **核心方法**：`_retrieve_context` (Base 层面定义接口，子类或 Delegate 实现)。

---

## 8. 文档同步更新计划 (Documentation Updates)

重构完成后，需同步更新以下技术文档，确保文档与代码实现保持一致：

### 1. `docs/ARCHITECTURE.md` (系统架构)

- **核心组件路径**：更新 `📋 运作基石` 章节中的文件路径，指向新的 `src/engine/core/`, `src/engine/generators/` 等目录。
- **工作流描述**：修订 QA 和 Design 生成流程，说明 `BaseGenerator` 的调度逻辑及 RAG 模块的独立性。
- **Prompt 引用**：更新文中提到的所有 `.txt` 提示词模板路径为新的场景化路径。

### 2. `docs/CONFIGURATION.md` (配置手册)

- **Prompt 配置说明**：新增章节说明如何通过 `configs/prompts/` 目录进行提示词定制，以及 `BaseGenerator` 如何加载这些模板。
- **语言档案说明**：详细说明 `configs/language/*.yaml` 中 `system_prompts` 角色的配置方法。

### 3. `docs/pipeline/` (步骤详情)

- **02-method-understanding-step.md**: 更新使用的类名和 Prompt 路径。
- **03-question-answer-step.md**: 更新 RAG 模块与生成器分离后的调用关系描述。
- **04-design-generation-step.md**: 更新架构约束注入的逻辑描述。

---

## 9. 预期效果 (Expected Outcome)

- 代码逻辑行数预计减少 40%-50%。
- 新增语言或修改业务规则时，**无需修改一行 Python 代码**。

---

## 10. 详细执行步骤与依赖关系 (Detailed Execution Steps)

本节列出了重构的原子化步骤及相互间的依赖关系，建议按阶段顺序执行。

### [STEP 1] 基础设施与提示词预置 (Pre-requisites)
>
> **目标**：在不改变逻辑的前提下，将所有“燃料”（提示词、配置）备好。

1. **配置补全**：在 `configs/language/*.yaml` 中新增 `system_prompts.{scenario}_role` 字段。
    - *依赖*：无。
2. **负向规则迁移**：创建 `configs/prompts/qa_rule/negative_rules.yaml` 并将代码中的规则转录。
    - *依赖*：无。
3. **Prompt 目录重组**：执行文件移动与重命名（对照第 5 节表）。
    - *依赖*：无。
4. **Prompt 骨架化**：将迁移后的 `.txt` 模板转换为占位符格式（`{role_identity}`等）。
    - *依赖*：步骤 3。

### [STEP 2] 基座开发 (Core Development)
>
> **目标**：建立新的生命周期与提示词渲染管线。

1. **BaseGenerator 核心实现**：编写 `src/engine/core/base_generator.py`，实现配置解析与提示词拼装。
    - *依赖*：步骤 1。
2. **LLM 调用封装**：迁移并增强 `llm_client.py` 至 `core/`，收拢重试逻辑。
    - *依赖*：无。
3. **RAG 独立化**：提取 `src/engine/rag/retriever.py`，实现通用的检索逻辑。
    - *依赖*：无。

### [STEP 3] 业务生成器迁移 (Generator Refactoring)
>
> **目标**：逐一替换存量 Generator，确保功能一致。

1. **方法特征提取迁移** (`MethodProfile`)：重写 `MethodUnderstander`。
    - *依赖*：STEP 2。
2. **QA 场景迁移** (`QA_Rule`)：依次重写 `QuestionGenerator` 和 `AnswerGenerator`。
    - *依赖*：STEP 2。
3. **架构设计场景迁移** (`Arch_Design`)：依次重写 `DesignQuestionGenerator` 和 `SolutionGenerator`。
    - *依赖*：STEP 2。

### [STEP 4] 流程集成与验证 (Integration & Verification)
>
> **目标**：打通全链路，更新文档。

1. **Pipeline 适配**：修改 `src/pipeline/steps/*.py` 的引用路径。
    - *依赖*：STEP 3。
2. **全链路回归**：运行 `main.py` 完整流程并对比样本生成质量。
    - *依赖*：STEP 3。
3. **文档同步更新**：按照第 8 节计划进行全局文档修订。
    - *依赖*：所有步骤。

> [!IMPORTANT]
> **关键检查点**：在完成 [STEP 1] 后，应先确保存量代码仍能运行（通过临时修改路径配置），再进行 [STEP 2] 和 [STEP 3] 的逻辑替换。
