# Grounding 强化（调用链/依赖召回）（设计文档）

> 目标：在不推翻现有检索结构的前提下，补充“调用链/依赖”维度的 evidence 召回，降低跨模块漂移，提高回答可追溯性。

---

## 1. 现状审计（Audit）

- 当前检索：`question_answer.retrieval` 与 `design_questions.retrieval` 支持 symbol / vector / hybrid。
- 现有问题：
  - 召回主要基于单个 symbol 或局部上下文，缺少调用链关联。
  - 跨模块问题易出现“只引用入口符号”的证据偏差。
  - evidence_refs 与真实调用关系未对齐。

---

## 2. 目标架构（Target Architecture）

### 2.1 逻辑流向（增量）

```
Symbol Retrieval → Call/Dependency Expansion → Evidence Pool → LLM
```

### 2.2 核心策略

- **弱规则版本（默认）**：基于 `symbols.jsonl` 的 method source 做调用名匹配扩展（有限深度），不依赖 call_graph。
- **证据池合并**：将扩展结果加入 evidence_pool，避免只引用入口。
- **配置可控**：通过小配置控制开关、深度、上限，保持成本可控。

---

## 3. 迁移映射（Migration Mapping）

> 不新增顶层模块，仅扩展现有 `question_answer.retrieval` 与 `design_questions.retrieval`。

**配置新增（可选）：**

```yaml
question_answer:
  retrieval:
    mode: "hybrid"
    min_score: 0.2
    fallback_top_k: 6
    call_chain:
      enabled: false
      max_depth: 1
      max_expansion: 20

design_questions:
  retrieval:
    mode: "hybrid"
    fallback_top_k: 8
    call_chain:
      enabled: false
      max_depth: 1
      max_expansion: 20
```

**旧逻辑兼容：**

- `call_chain.enabled=false` 时保持当前检索行为不变。

---

## 4. 阶段性路径（Phases）

1) **影子配置**  
   增加 `call_chain.*` 配置，默认关闭。

2) **调用链扩展实现**  
   在 answer/design 生成阶段增加“扩展 evidence_pool”的逻辑。

3) **统计与回归**  
   在 retrieval report 中记录扩展命中数量与追加 evidence_refs 数量。

---

## 5. 决策平衡（Trade-offs）

| 方案 | 说明 | 优点 | 风险 |
| --- | --- | --- | --- |
| off | 维持现状 | 无新增成本 | 跨模块证据偏弱 |
| enabled（推荐） | 轻量扩展调用链 | evidence 更完整 | 上下文变大、成本提升 |
| aggressive | 深度扩展 | 覆盖更高 | 噪声与成本显著增加 |

---

## 6. 最终决策（已采用，demo 最小改动）

- **启用策略**：`enabled=true`（仅弱规则版本）。
- **扩展深度**：`max_depth=1`。
- **扩展规模**：`max_expansion=20`。
- **项目定位**：demo 项目，以最小改动验证效果，不追求完整调用图。
