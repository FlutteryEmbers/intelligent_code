# 生成侧多样性与场景化注入（设计文档）

> 目标：在**不新增顶层模块**的前提下，通过配置与 prompt 增量更新，让生成侧能按配额控制 question_type 多样性，并引入“模糊/指代问”等场景化问题，提升数据覆盖面。

---

## 1. 现状审计（Audit）

- 现有生成侧已支持 bucket/intent 抽样（`auto_question_generator.py` / `auto_design_question_generator.py`）。
- prompt 中列出 question_type，但**没有配额控制与采样逻辑**（`configs/prompts/*/auto_*_generation.txt`、`coverage_*_generation.txt`）。
- 现有逻辑未明确“模糊/指代问”比例，场景化注入不足。
- 分布闭环依赖 `coverage` 标签，**无法保证 question_type 多样性**。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Question Generation
  ├─ 先抽 bucket/intent（现有）
  ├─ 再抽 question_type（新增）
  └─ 按场景模板注入（新增）
```

### 2.2 核心策略

- **question_type 配额**：生成阶段按配额抽取 question_type，降低“全是解释类”的偏差。
- **场景化注入**：按比例引入“模糊问 / 指代问 / 省略上下文”的 prompt 片段。
- **兼容旧逻辑**：默认 `mode=off`，只在配置开启时生效。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展 `question_answer.coverage` 与 `design_questions.coverage`。

**配置新增（默认启用，demo 友好）：**

```yaml
question_answer:
  coverage:
    diversity:
      mode: "quota"          # off | quota
      question_type_targets:
        how_to: 0.2
        config: 0.15
        flow: 0.15
        auth: 0.1
        error: 0.15
        deploy: 0.1
        impact: 0.05
        perf: 0.05
        consistency: 0.03
        compatibility: 0.02
        edge: 0.0
    scenario_injection:
      mode: "ratio"          # off | ratio
      fuzzy_ratio: 0.2       # 模糊/指代问比例
      templates_path: "configs/user_inputs/qa_scenario_templates.yaml"

design_questions:
  coverage:
    diversity:
      mode: "quota"
      question_type_targets:
        architecture: 0.25
        integration: 0.2
        consistency: 0.15
        error_handling: 0.15
        performance: 0.1
        security: 0.1
        maintenance: 0.1
    scenario_injection:
      mode: "ratio"
      fuzzy_ratio: 0.15
      templates_path: "configs/user_inputs/design_scenario_templates.yaml"
```

**旧逻辑兼容：**

- 未配置时等价于 `diversity.mode=off`、`scenario_injection.mode=off`，保持当前行为。

---

## 4. 实施环节（Phases）

1) **配置落地（默认启用 quota/ratio）**  
   在 `configs/launch.yaml` 写入 `diversity` 与 `scenario_injection`，并使用推荐配额与比例。

2) **生成侧抽样逻辑**  
   在 `auto_question_generator` / `auto_design_question_generator` 中新增 question_type 抽样与场景模板拼接。

3) **提示词扩展**  
   在 `prompts.*` 中增加“question_type/场景要求”段落，确保 LLM 输出匹配。

4) **统计验证**  
   在 `coverage_report` 或 `pipeline_summary` 中输出 question_type 分布（可选），对齐配额预期。

---

## 5. 决策平衡（Trade-offs）

| 方案 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| off | 维持现状 | 零风险 | 多样性偏低 |
| quota（推荐） | 生成前抽 question_type | 分布可控 | 需要模板与抽样逻辑 |
| downstream-only | 仅在抽样阶段控制 | 实现最小 | 生成侧仍偏置，候选不足 |

---

## 6. 最终决策（已采用）

- **diversity.mode**：`quota`
- **question_type_targets**：使用推荐默认值
- **scenario_injection.mode**：`ratio`
- **fuzzy_ratio**：QA=0.2、Design=0.15
- **模板来源**：新增模板文件（最小新增）

---

## 7. 影响范围（代码/配置）

- **配置**：`configs/launch.yaml`（不新增顶层模块）
- **生成逻辑**：`src/engine/auto_question_generator.py`、`src/engine/auto_design_question_generator.py`
- **prompt**：`configs/prompts/question_answer/*`、`configs/prompts/design/*`
- **报告**：`coverage_report` 不变，但可新增 question_type 统计（可选）

---

## 8. 必要实施清单（最小改动）

1) `configs/launch.yaml` 增加 `diversity` 与 `scenario_injection` 配置。  
2) `src/engine/auto_question_generator.py` 与 `src/engine/auto_design_question_generator.py` 实现 question_type 抽样与场景注入。  
3) 新增 `configs/user_inputs/*_scenario_templates.yaml`（最小模板集合）。  
4) 更新 `configs/prompts/*` 的生成提示，要求输出 `question_type` 与场景化约束。  
