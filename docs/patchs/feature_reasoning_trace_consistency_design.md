# Reasoning Trace 结构化一致性（设计文档）

> 目标：在不推翻现有流程的前提下，补齐 Reasoning Trace 的结构化一致性，确保生成内容包含稳定的推理结构，并与证据对齐。

---

## 1. 现状审计（Audit）

- 已有结构：`ReasoningTrace` 在 schema 中存在，`validator` 进行字段与数量校验。
- 现有不足：
  - Prompt 未强制固定结构（Analysis/Evidence/Decision 等）。
  - Trace 与 answer 语义一致性未校验。
  - trace 锚定规则（File:L#Line）没有被强制要求。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Prompt 生成 → LLM 输出 → Validator Trace 校验 → Quality Gate → Merge
```

### 2.2 核心策略

- **结构统一**：Prompt 中要求固定结构字段（Observations/Inferences/Assumptions + Evidence）。
- **锚定要求**：Evidence 需要包含 `(file_path, line range)` 信息或可映射的 evidence_refs。
- **一致性校验**：新增轻量一致性检查（trace 中的结论必须支持 answer 的主张）。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展现有 `quality.trace_rules` 与 prompt。

**配置新增（可选）：**

```yaml
quality:
  trace_rules:
    mode: "warning"               # warning | reject
    require_trace_structure: true # NEW: 强制结构化字段
    require_evidence_anchor: true # NEW: 强制 evidence_refs 对齐
    require_answer_alignment: false # NEW: 轻量一致性检查
```

**旧逻辑兼容：**

- 未配置时默认关闭新增校验；仅保留现有校验逻辑。

---

## 4. 阶段性路径（Phases）

1) **影子配置**  
   增加新规则开关，但默认关闭。

2) **Prompt 约束落地**  
   在 QA/Design prompts 中加入结构化字段要求。

3) **校验增强**  
   在 validator 中按配置启用结构化一致性检查。

---

## 5. 决策平衡（Trade-offs）

| 方案 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| warning | 只警告 | 不影响产出 | 一致性约束弱 |
| reject | 直接拒绝 | 结构质量提升 | rejected 比例上升 |

---

## 6. 影响范围（代码/配置）

- **配置**：`configs/launch.yaml`（扩展 quality.trace_rules）
- **Prompt**：`configs/prompts/question_answer/*`、`configs/prompts/design/*`
- **校验**：`src/utils/validator.py`（新增一致性校验）
- **报告**：`qa_quality.json` / `design_quality.json` 新增 trace 统计字段（可选）

---

## 7. 需要你确认的决策

1) trace 校验默认是 warning 还是 reject  
2) 是否启用 answer-alignment 校验（demo 建议先关闭）  
3) 是否要求 evidence anchor（默认开启）  

