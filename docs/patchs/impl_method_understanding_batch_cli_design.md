# Method Understanding 批处理（launch.yaml 驱动，无 CLI）设计补丁

> 目标：避免长时间连续运行导致 Windows 黑屏；由 **launch.yaml 接管批处理与跳过策略**，彻底废弃 CLI 作为配置入口。

---

## 1. 现状审计（Audit）

### 1.1 当前逻辑分布
- 入口：`src/pipeline/steps/method_understanding.py`
- 生成器：`src/engine/auto_method_understander.py`
- 配置读取：
  - `method_understanding.max_methods`
  - `core.max_context_chars`（全局统一）
  - `method_understanding.prompts.generation`
- 输出工件：
  - `artifacts.method_profiles_jsonl`
  - `artifacts.auto_method_understanding_rejected_jsonl`

### 1.2 运行特征与风险点
- 当前为**单次长跑**：一次性处理 Top‑K 候选方法，缺乏批次拆分。
- 输出为 **覆盖写入**：重复执行会覆盖历史结果，不具备增量能力。
- 批处理与跳过能力分散，缺少配置侧统一入口。

### 1.3 耦合点
- `question_answer` 依赖 `method_profiles_jsonl` 与 embeddings 构建。
- `design_questions` 在 `use_method_profiles=true` 时依赖 profiles。

---

## 2. 目标架构（Target Architecture）

### 2.1 设计目标
- 使用 **launch.yaml** 接管批处理与跳过策略（配置为主，CLI 不参与）。
- 保持现有默认行为不变（未开启批处理时仍是全量处理）。
- 支持“短时多次运行”，降低长时间高负载风险。

### 2.2 新逻辑流向
1) `launch.yaml` 指定 `batching.enabled` 与 `batch_size`
2) MethodUnderstandingStep 仅处理本次批次上限
3) 输出按 `output_mode` 选择 **覆盖/追加**
4) `resume=true` 时跳过已处理方法（无需 batch_index）

### 2.3 配置约定（示意）

```yaml
method_understanding:
  enabled: true
  max_methods: 300
  prompts:
    generation: "configs/prompts/method_understanding/auto_method_understanding.txt"
  batching:
    enabled: false
    batch_size: 50
    output_mode: "overwrite"   # overwrite | append
    resume: false               # true 时跳过已存在的 symbol_id
```

> 说明：
> - `batch_size` 表示单次运行的处理上限；未开启 batching 则保持全量行为。
> - `output_mode=append` + `resume=true` 对应“持续追加”的需求；`overwrite` 对应“重新创建”。
> - 不使用 `batch_index`，由 `resume` 自动推进。

---

## 3. 迁移映射（Migration Mapping）

| 旧方式 | 新方式 | 说明 |
| --- | --- | --- |
| 无批处理 | `method_understanding.batching.*` | 配置接管批处理入口 |
| 覆盖写入 | `batching.output_mode=overwrite` | 默认行为保持不变 |
| 手动跳过 | `method_understanding.enabled=false` | 唯一跳过入口 |
| 追加生成 | `output_mode=append + resume=true` | 无需 batch_index |

---

## 4. 阶段性路径（Phases）

### Phase 1：配置驱动批处理
- 增加 `method_understanding.batching.*`
- 默认不启用，行为与当前一致

### Phase 2：追加与自动推进
- 启用 `output_mode=append` 与 `resume=true`
- 多次运行自动跳过已处理方法，追加新结果

### Phase 3：可选增强
- 追加运行的去重统计与报告（仅限可选增强）

---

## 5. 决策平衡（Trade-offs）

| 方案 | 优点 | 缺点 | 适用场景 |
| --- | --- | --- | --- |
| 配置驱动批处理 | 入口统一、可复现 | 需编辑 launch.yaml | Demo/截止期优先 |
| 追加但不 resume | 实现最简单 | 可能产生重复 | 临时验证 |
| 追加 + resume | 无需 batch_index，自动推进 | 需要读取已有工件 | 稳定后长期使用 |

**决策结果（当前选择）**：采用“配置驱动批处理”，其余方案保留为后续可选优化。

---

## 结论

- 彻底废弃 CLI 作为配置入口，由 launch.yaml 统一管理批处理策略。
- 通过 `output_mode=append` / `overwrite` 与 `resume` 实现“追加或重建”的运行语义。
- 保持默认行为不变，满足 demo 项目低风险增量更新诉求。
