# 生成侧多样性分布回归（question_type 报告与回归验证）（设计文档）

> 目标：在不新增顶层模块的前提下，输出 question_type 分布报告并提供回归校验能力，验证生成侧多样性配额是否生效。

---

## 1. 现状审计（Audit）

- 生成侧已有 question_type 抽样逻辑（`_sample_question_type`）。
- 现有报告缺少 question_type 分布统计，无法回归校验多样性配额。
- coverage_report 仅统计 bucket/intent/module_span/polarity。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Question Generation → Validation(clean) → Coverage Tagger → Coverage Sampler
                     → QuestionType Reporter → reports/question_type_report.json
```

### 2.2 核心策略

- **统计来源**：从 clean 样本中统计 `question_type` 分布（QA/Design 分开）。
- **配额对齐**：与 `coverage.diversity.question_type_targets` 做差异对比。
- **回归验证**：当偏差超过阈值时输出 warning（可选 fail）。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展 `question_answer.coverage.diversity` 与 `design_questions.coverage.diversity`。

**配置新增（可选）：**

```yaml
question_answer:
  coverage:
    diversity:
      mode: "quota"
      question_type_targets: {...}
      regression:
        enabled: true
        max_delta: 0.1

design_questions:
  coverage:
    diversity:
      mode: "quota"
      question_type_targets: {...}
      regression:
        enabled: true
        max_delta: 0.1

artifacts:
  question_type_report_json: "data/reports/question_type_report.json"
```

**旧逻辑兼容：**

- 未配置时默认不输出 report、不做校验。

---

## 4. 阶段性路径（Phases）

1) **影子配置**  
   新增 `regression` 配置并默认关闭。

2) **统计输出**  
   在 pipeline 后处理阶段输出 `question_type_report.json`。

3) **回归校验**  
   若 enabled，计算偏差并输出 warning（可选 fail-fast）。

---

## 5. 决策平衡（Trade-offs）

| 方案 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| off | 不做回归 | 零成本 | 无法验证配额 |
| warn-only（已选） | 超阈值报警 | 可追踪 | 不阻断流程 |
| fail-fast | 超阈值直接失败 | 严格对齐 | 容易中断 demo |

---

## 6. 最终决策（已采用）

- **回归策略**：warn-only  
- **默认阈值**：`max_delta=0.1`  
- **项目定位**：demo 项目，不做 fail-fast  
