# 推理链路补强：反例对比与架构约束注入（设计文档）

> 目标：在不改动主流程的前提下，让生成结果显式包含“反例对比（为何不选其他方案）”与“架构约束引用”，提升推理可解释性与一致性。

---

## 1. 现状审计（Audit）

- 反例对比缺失：当前 prompts 未要求输出“为何不采用其他方案”的对比论证。
- 架构约束缺失：生成逻辑未引用项目的架构规则/约束集（无明确来源）。
- 现有能力：ReasoningTrace 已结构化，且存在可扩展的 prompt 模板体系。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Prompt 生成（加入反例&约束段） → LLM 输出 → Validator（可选一致性检查）
```

### 2.2 核心策略

- **反例对比段落**：要求在 answer 中包含 “Rejected Alternatives / Why Not”。
- **约束注入段落**：从配置中读取“架构约束条目”，插入 prompt 作为硬性参考。
- **最小侵入**：仅新增配置与 prompt 片段，不新增顶层模块。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展 `question_answer` / `design_questions` 与 `core` 或 `quality`。

**配置新增（可选）：**

```yaml
core:
  architecture_constraints_path: "configs/prompts/common/arch_constraints.yaml"

question_answer:
  constraints:
    enable_counterexample: true
    enable_arch_constraints: true

design_questions:
  constraints:
    enable_counterexample: true
    enable_arch_constraints: true
```

**旧逻辑兼容：**

- 未配置时不影响现有行为，prompt 不增加额外段落。

---

## 4. 阶段性路径（Phases）

1) **影子配置**  
   增加约束配置与 constraints 文件路径，默认关闭。

2) **Prompt 段落注入**  
   在 QA/Design 的 answer prompt 中加入“反例对比/架构约束”段落，受开关控制。

3) **一致性校验（可选）**  
   在 validator 中增加轻量校验（如关键字检查），确保段落存在。

---

## 5. 决策平衡（Trade-offs）

| 方案 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| off | 不注入 | 零成本 | 推理深度弱 |
| prompt-only（已选） | 仅 prompt 强制段落 | 改动小 | 依赖模型遵循 |
| prompt+validator | 约束更强 | 输出稳定 | rejected 上升 |

---

## 7. 最终决策（已采用）

- **方案**：prompt-only
- **范围**：QA 与 Design prompts 同步添加“反例对比/架构约束”段落
- **校验**：不新增 validator 校验（保持最小改动）

## 6. 影响范围（代码/配置）

- **配置**：`configs/launch.yaml`、`configs/prompts/common/arch_constraints.yaml`
- **Prompt**：`configs/prompts/qa_rule/*`、`configs/prompts/arch_design/*`
- **校验（可选）**：`src/utils/data/validator.py`
