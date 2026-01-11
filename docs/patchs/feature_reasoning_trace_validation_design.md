# Reasoning Trace 结构化校验（实现级设计）

遵循 `docs/ai_rules/design/ai_design_rules.md`：增量优先、配置复用、决策透明、仅做设计。

---

## 1. 现状审计（Audit）

### 1.1 现有逻辑分布

- **数据结构**：`src/utils/schemas.py` 定义 `ReasoningTrace`（observations/inferences/evidence_refs/assumptions）。
- **校验入口**：`src/utils/data/validator.py` 仅验证 evidence_refs 一致性与 schema 通过，不校验 trace 结构质量。
- **Prompt 约束**：当前 prompt 未强制 trace 的结构化输出与字段一致性。

### 1.2 冗余与耦合

- 现有 quality gate 与 trace 质量无直接耦合。
- 若单独新增校验 step，可能与 ValidationStep 重复扫描样本。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
... → ValidationStep(quality gate) → Merge → ...
```

- 在 **ValidationStep/validator** 内新增 trace 结构校验（不新增 pipeline step）。
- 结果写入 `quality.checks.trace`，按 `quality.fail_on_warnings` 决定拒绝或警告。

### 2.2 校验目标（最小可用）

- **结构完整性**：
  - observations / inferences 至少其一非空
  - evidence_refs 与 observations/inferences 的数量关系不为 0/0
- **一致性**：
  - evidence_refs 不为空时，trace 字段不能全空
- **格式稳定性**：
  - observations/inferences/assumptions 仅允许字符串列表

---

## 3. 迁移映射（Migration Mapping）

不新增顶层模块，仅复用 `quality`：

- 旧 Key → 新 Key
  - `quality.*` → `quality.trace_rules.*`（新增可选字段）
  - `quality.fail_on_warnings` 继续生效

兼容策略：未配置 trace_rules 时保持旧行为（不拒绝，只记录 warning）。

---

## 4. 阶段性路径（Phases）

### Phase 1（影子校验）

- 只记录 trace 校验结果（warning），不影响 clean 产出。
- 目标：统计缺口与误杀率。

### Phase 2（软 gate）

- trace 不合格写 warning，按 `quality.fail_on_warnings` 决定是否拒绝。
- 默认仍保持 warning-only（demo 友好）。

### Phase 3（硬 gate）

- 对关键场景（如 arch_design）开启硬拒绝。
- 仅在 trace 质量稳定后切换。

---

## 5. 决策平衡（Trade-offs）

### 决策 1：校验入口放哪里

放到 ValidationStep 内（推荐） | 改动最小，与质量门统一 | validator 逻辑更复杂 |


### 决策 2：策略开关位置与模式

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| `trace_rules.mode=warning`（demo 推荐） | 不影响产量 | trace 质量提升较慢 |
| `trace_rules.mode=reject` | 质量提升快 | rejected 增加 |

兼顾两者，模式切换用mode

### 决策 3：校验范围（demo 默认）

- **方案 A：QA + Design 全部启用（推荐）**
  - 优点：统一行为，便于统计。
  - 代价：QA 样本 rejected 可能增加。

默认值（demo）：采用 A。

### 决策 4：触发条件（demo 默认）

- **方案 A：所有样本都校验（推荐）**
  - 优点：规则简单，统计一致。
  - 代价：会对低信息样本产生更多 warning。

默认值（demo）：采用 A。

### 决策 5：上限策略（demo 默认）

- **方案 A：启用 max_* 约束（推荐）**
  - 优点：防止 trace 冗长，控制噪声。
  - 代价：可能误杀详细样本。
- **方案 B：仅最小值校验**
  - 优点：更保守。
  - 代价：冗长 trace 可能拖累质量。

默认值（demo）：采用 A。

---

## 6. 配置建议（复用现有模块）

```yaml
quality:
  fail_on_warnings: false
  trace_rules:
    mode: "warning"               # warning | reject
    scope: "all"                  # all | arch_design
    require_evidence_refs: false  # false=所有样本校验
    require_non_empty: true       # observations/inferences 至少一个非空
    require_evidence_alignment: true
    min_observations: 1
    min_inferences: 1
```

### trace_rules 示例（完整示意）

```yaml
quality:
  fail_on_warnings: false
  trace_rules:
    mode: "warning"
    scope: "all"
    require_evidence_refs: false
    require_non_empty: true
    require_evidence_alignment: true
    min_observations: 1
    min_inferences: 1
    max_observations: 8
    max_inferences: 8
    max_assumptions: 5

说明：trace 相关统计写入 `qa_quality.json` / `design_quality.json`（quality 报告）。
```

---

## 7. 验收标准

- trace 相关 warning 在报告中可见且可统计。
- 不配置 trace_rules 时旧流程无变化。
- 配置开启后 rejected 增量可控，且与缺口分析一致。
