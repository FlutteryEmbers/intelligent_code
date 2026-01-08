# 覆盖分布闭环补全（增量设计）

目标：在**不改动现有 pipeline 结构**的前提下，补齐覆盖分布的闭环能力，重点是：

- 报表字段完善（coverage_report）
- 采样配置校验与兜底

---

## 1. 现状与问题

### 1.1 现状

- 已存在 coverage tagger + sampler 的 pipeline 步骤。
- 已产出 `coverage_report.json`。
- 配置中已有 `question_answer.coverage.*` 与 `design_questions.coverage.*`。

### 1.2 核心问题

- 报表字段不够完整（缺 intent/module_span 分布、缺口原因）。
- 采样目标在运行时可能失效（targets 为空或为 0 时退化为均分）。
- 配置校验缺少明确提示，难以定位“用错配置路径”的问题。

---

## 2. 闭环补全的目标输出

### 2.1 报表字段（建议增量）

`coverage_report.json` 最小字段：

- **targets**：有效采样权重（归一化后）
- **raw_targets**：原始配置值（便于排错）
- **used_default_targets**：是否使用默认兜底
- **bucket_distribution**：high/mid/hard 实际占比
- **intent_distribution**：intent 维度占比
- **module_span_distribution**：single/multi 占比
- **deficits/borrowed**：抽样缺口与补齐来源

### 2.2 采样配置校验

- 发现 targets 不合法时 **warning** 记录并回退默认 80/15/5。
- 同时在报表中记录 `used_default_targets=true`。
- 采样目标校验不改变现有生成逻辑，只提升可观测性。

---

## 3. 增量更新范围（尽量贴合现有项目）

### 3.1 逻辑范围

- **报表扩展**：在 CoverageSampler 输出中补齐统计字段。
- **校验提示**：当 targets 缺失/为 0 时输出 warning。

### 3.2 配置范围（不新增顶层模块）

- 复用现有字段：
  - `question_answer.coverage.targets`
  - `design_questions.coverage.targets`
  - `artifacts.coverage_report_json`
- 不新增顶层模块，仅在现有 coverage 内追加**可选**字段时需明确兼容策略。

---

## 4. 需要你做的决策（含 trade-offs）

### 决策 1：报表是否包含 intent/module_span 分布

- **方案 A：包含（推荐）**
  - 优点：闭环更完整，可定位“高频/长尾缺口”来源。
  - 代价：报表体积稍增，需要 tagger 保证字段齐全。
  - 默认值（demo）：采用 A。

### 决策 2：targets 不合法时的行为

- **方案 A：warning + 回退默认（推荐）**
  - 优点：不中断 pipeline，结果可预测。
  - 代价：可能掩盖配置路径错误（但报表可追踪）。
  - 默认值（demo）：采用 A。

### 决策 3：采样报告是否区分 QA/Design

- **方案 A：分开（推荐）**
  - 优点：符合当前 pipeline 分离结构。
  - 代价：报表字段重复。
  - 默认值（demo）：采用 A。

### 决策 4：统计口径（基于哪一阶段数据）

- **方案 A：抽样后（推荐）**
  - 优点：最贴近最终训练集。
  - 代价：偏差来源诊断较弱。
- **方案 B：抽样前**
  - 优点：更易诊断供给不足。
  - 代价：与最终训练集略有偏差。
  - 默认值（demo）：采用 A。

### 决策 5：标签缺失处理

- **方案 A：归入 high（推荐）**
  - 优点：实现简单，保持总量稳定。
  - 代价：可能掩盖打标缺失。
- **方案 B：归入 unknown**
  - 优点：问题更容易暴露。
  - 代价：需要额外统计逻辑。
  - 默认值（demo）：采用 A。

### 决策 6：小样本阈值

- **方案 A：小样本跳过严格配额（推荐）**
  - 优点：避免随机噪声放大。
  - 代价：比例不稳定。
- **方案 B：强制比例**
  - 优点：始终符合目标。
  - 代价：小样本波动很大。
  - 默认值（demo）：采用 A。

---

## 5. 实施建议（不改代码时的落地方式）

1) 先补充设计文档并确认决策。
2) 在 `coverage_report.json` 预留字段（即使暂时为空，也明确格式）。
3) 配置说明中强调 targets 为空会触发 warning 与 default。

---

## 6. 验收标准（闭环补全）

- 报表可明确回答：
  - 目标分布是否生效？
  - 实际分布与目标偏差？
  - 偏差来自缺口还是配置失效？
- 配置缺失时可追踪，不“静默均分”。
