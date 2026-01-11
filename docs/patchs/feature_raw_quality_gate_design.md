# Quality Gate 设计方案（从 report-only 到可训练强保证）

本文档给出一个尽可能贴合当前项目的 Quality Gate（质量闸门）演进方案：在保留现有 `ValidationStep` 报告能力的基础上，把“校验结果”升级为可被后续步骤消费的 **clean 训练数据主干**，并通过模块化的检查器体系持续扩展质量标准。

目标：让最终导出的 `data/final/*_sft.jsonl` 在 **逻辑正确性（证据一致）**、**合规性（安全扫描）**、**代表性/多样性** 上更可控、更可回归。

---

## 1. 现状与问题定位

### 现状（当前实现）

- `ValidationStep` 会对 `auto_qa_raw.jsonl`（兼容 `qa_raw.jsonl`）与 `design_raw.jsonl` 做：
  - Pydantic schema 校验（`TrainingSample`）
  - `thought.evidence_refs` 一致性校验（symbol_id、source_hash、file_path、commit）
  - 输出 `qa_quality.json` / `design_quality.json` + `data/intermediate/rejected/*_validation_rejected.jsonl`
- 但 Validation 是 **report-only**：不会产出可供后续消费的 `*_clean.jsonl`，后续 `Merge/Dedup/Safety/Split/Export` 仍以 raw 为准。
- MergeStep 读取 `artifacts.auto_qa_raw_jsonl`（并兼容 legacy `qa_raw.jsonl`），将其与 `design_raw.jsonl` 合并进入 `all_raw.jsonl`。

对应文档与代码参考：

- `docs/pipeline/05-validation-step.md`
- `src/pipeline/steps/validation.py`
- `src/utils/data/validator.py`
- `src/pipeline/steps/merge.py`（Auto QA 输入选择逻辑）

### 主要问题

- **训练集强保证不足**：即使 validation 报告失败，样本仍可能进入最终训练集。
- **质量字段未被利用**：`TrainingSample.quality` 是“后续填充”，但目前基本为空，无法用于过滤/抽样/诊断。
- **质量规则分散**：长度/格式等“软质量”阈值在 `configs/launch.yaml` 的 `quality:` 中已定义，但未真正形成 gate。
- Auto QA 已纳入 Validation，但仍是 report-only，无法阻止低质样本进入最终训练集。

---

## 2. 设计目标（What good looks like）

1) **强保证主干**：产出 `*_clean.jsonl`，后续步骤默认消费 clean（raw 仅用于回放与调参）。
2) **模块化可扩展**：把检查拆为独立 gate/checker，便于新增/替换（例如新增“架构设计样本证据覆盖最小数”规则）。
3) **可观测可回归**：报告不仅统计 pass rate，还能定位失败类型、失败样本、各场景分布，支持回归比较。
4) **兼容现有 pipeline**：尽量不改变 step 顺序与工件语义；优先在 ValidationStep 内升级输出与消费路径。
5) **适配 Auto/非 Auto**：无论 QA 来源是 `auto_qa_raw.jsonl` 还是 legacy `qa_raw.jsonl`，都能进入同一套 gate。

---

## 3. 核心方案（推荐实现）

### 3.1 Gate 输出工件（Artifacts）扩展：raw → clean + rejected + report

在 `data/intermediate/clean/` 新增 clean 主干工件（与现有 rejected/auto_questions 目录对齐）：

- `clean/qa_clean.jsonl`：通过 gate 的 QA 样本（TrainingSample dict，带 `quality`，auto/user 不区分文件名）
- `clean/design_clean.jsonl`：通过 gate 的 Design 样本

保留现有 rejected 与 report：

- `data/intermediate/rejected/qa_validation_rejected.jsonl`、`data/intermediate/rejected/design_validation_rejected.jsonl`
- `data/reports/qa_quality.json`、`data/reports/design_quality.json`

> 关键变化：后续 `MergeStep` 优先读取 `*_clean.jsonl`，实现“强保证主干”。

### 3.2 `TrainingSample.quality` 的最小契约（不破坏兼容性）

不新增强类型 schema（保持 `dict`），但约定最小字段，便于后续消费：

```json
{
  "gate_version": "v1",
  "passed": true,
  "errors": [{"code": "EVIDENCE_MISSING", "message": "..."}],
  "warnings": [{"code": "RANGE_LARGE", "message": "..."}],
  "checks": {
    "schema": "pass",
    "evidence": "pass",
    "commit": "pass",
    "length": "pass",
    "scenario_rules": "pass"
  },
  "stats": {
    "context_chars": 1234,
    "answer_chars": 567
  }
}
```

说明：

- **pass/fail 的唯一来源是 quality**：clean 文件只写 `passed=true` 的样本。
- `errors/warnings` 用 `code` 归类，便于报告聚合（替代当前“按字符串前缀切分”的脆弱策略）。
- `stats` 用于后续分析分布（长度、evidence 数等）。

### 3.3 Gate 检查器分层（模块化）

将检查拆为两类：**Hard Gate（硬拒绝）** 与 **Soft Gate（软评分/告警）**：

- Hard Gate（失败直接拒绝进入 clean）：
  - `SchemaGate`：`TrainingSample` Pydantic 校验
  - `EvidenceGate`：`thought.evidence_refs` 命中与 hash/path/line 校验
  - `SafetyHardGate`（可选）：明显敏感信息命中则拒绝（或仍由 `SecretsScanStep` 统一处理）
- Soft Gate（可配置为 warn 或 reject）：
  - `LengthGate`：复用 `configs/launch.yaml:quality`（min/max 长度）
  - `CommitGate`：commit 不一致仅记 warning（避免误杀历史分支样本）
  - `ScenarioGate`：按 `scenario` 添加规则
    - `qa_rule`：要求 evidence_refs >= 1；context 不为空；问题不重复（可后置到 Dedup）
    - `arch_design`：要求 evidence_refs >= `design_questions.min_evidence_refs`（作为 design_generator.require_min_evidence 的来源）；上下文需覆盖至少 N 个层级（可从 file_path/qualified_name 统计）
  - `TraceShapeGate`：检查 `thought.observations/inferences` 的基本形态（例如不能为空、条数上限、是否包含“无依据猜测”模板词等）

> 推荐策略：第一期把 Soft Gate 默认设为 warning（不影响数据量），并通过 report 观察分布后再逐步转为 reject。

---

## 4. 技术选项与取舍

### 4.1 Gate 放在哪个阶段？

选项 A（推荐）：**保持现有位置（ValidationStep，merge 前）**  
优点：尽早过滤垃圾样本，减少后续 dedup/safety/split 的负担；与现有文档/实现贴合。  
缺点：需要确保 Auto QA 也产出 clean（当前 Validation 已兼容 auto_qa_raw）。

选项 B：在 merge 后新增 `QualityGateStep`（all_raw 级别）  
优点：对所有来源统一处理（QA、Design、Auto 等），逻辑更集中。  
缺点：改动更大（新增 step、调整文档与工件流转），不符合“尽量贴合当前项目”的约束。

结论：先做 A（小改动），未来如规模变大再考虑 B。

### 4.2 clean 工件如何产出？

选项 A（推荐）：**新增 clean 文件，不覆写 raw**  
优点：可回放/对比/调参；与现有 rejected/report 结构一致。  
缺点：磁盘多一份数据。

选项 B：覆写 raw（只保留 clean）  
优点：后续步骤无需改动。  
缺点：丢失 raw，调试困难；与“报告型 validation”初衷冲突。

结论：选 A，后续步骤只做“优先消费 clean”的小改动；是否允许 fallback 由 `quality.gate_mode` 控制（`gate` 禁止回退，`report` 允许回退）。

### 4.3 质量判断：规则 vs LLM Judge

选项 A（推荐一期）：**规则/统计驱动**  
覆盖 schema/evidence/长度/结构等；稳定、可复现、成本低。

选项 B（二期可选）：LLM Judge（例如用本地 Ollama）  
可对“幻觉/不基于 context”做更强判断，但成本高、稳定性与可复现性差，需要缓存与版本固定。

结论：先把“可验证的硬指标”做强（Evidence-first），Judge 作为可选增强写入路线图。

---

## 5. 实施步骤（按阶段落地，尽量小步可回归）

### Phase 1（最小可用）：从 report-only 升级为 gate

1) **扩展 paths**
   - 在 Orchestrator 的 `self.paths` 增加 `clean/qa_clean_jsonl`、`clean/design_clean_jsonl`
   - 在 `configs/launch.yaml:artifacts` 增加对应 clean 路径，确保下游读取一致
2) **扩展 validate_dataset 输出**
   - 在 `src/utils/data/validator.py` 增加 `clean_path` 输出，并把 `quality` 写回样本（写入 clean）
3) **ValidationStep 覆盖 Auto QA**
   - 与 `MergeStep` 对齐：优先 `artifacts.auto_qa_raw_jsonl`，兼容 legacy `qa_raw.jsonl`
4) **MergeStep 优先消费 clean**
   - 若 `clean/qa_clean.jsonl` 存在则使用，否则按 `quality.gate_mode` 决定是否 fallback 到 raw；Design 同理
5) **报告不变**
   - 保留 `qa_quality.json` / `design_quality.json`，并在其中新增 clean 输出路径与 gate 版本信息

验收标准（最小）：

- 同一份输入 raw，能稳定产出 clean/rejected/report 三套工件
- Merge 后的数据只来自 clean（在 clean 存在时）
- pass_rate 与 rejected 的数量在报告中可追踪

### Phase 2（模块化）：把校验拆成可组合的 gates

1) 新增 `src/utils/quality_gate/`（或在 `validator.py` 内先拆函数也可）
2) 定义统一接口：
   - `check(sample, symbols_map, config) -> CheckResult(passed, errors, warnings, stats)`
3) 将现有 evidence/commit/范围检查迁移为独立 gate
4) 新增 `LengthGate`，复用 `configs/launch.yaml:quality` 的阈值
5) 报告按 `error.code` 聚合

### Phase 3（场景约束）：对 `qa_rule` 与 `arch_design` 添加可配置规则

建议优先落地：

- `arch_design`：
  - evidence_refs 数量下限（默认沿用 `design_questions.min_evidence_refs`）
  - context 是否覆盖多层（按 file_path/qualified_name 的 top-level 目录或 package 前缀统计）
- `qa_rule`：
  - instruction 必须是问句/包含疑问意图（可用简单规则，不做 NLP 依赖）
  - answer 中必须包含“基于代码上下文”的关键片段（例如引用到具体类/方法名，先做软告警）

### Phase 4（可选增强）：LLM Judge + 缓存

- 仅对已通过 Hard Gate 的样本进行 Judge（减少成本）
- 将 judge 结果写入 `quality.scores/judge`，默认作为 warning，不直接拒绝
- 引入缓存 key：`sha256(instruction+context+answer+judge_prompt+judge_model_version)`

---

## 6. 与现有步骤的边界（避免重复与冲突）

- **DeduplicationStep**：去重应保持在 merge 之后；Quality Gate 只做“硬错误拒绝”与“长度/结构”类检查，避免重复实现 simhash。
- **SecretsScanStep**：继续作为“上线前最后一道安全门”。若 Phase 1 引入 `SafetyHardGate`，也应保持规则一致，避免同一类问题在两个 step 里出现相反结论。
- **SplitStep**：依赖 evidence_refs 做分组；Quality Gate 强化 evidence_refs 的存在性会直接提升 split 的有效性与泄漏控制能力。

---

## 7. 配置建议（与当前 launch.yaml 贴合）

建议在 `configs/launch.yaml` 中新增（或复用已有字段）：

```yaml
quality:
  gate_mode: "gate"               # report | gate
  write_clean: true
  allow_fallback_in_report: true  # mode=report 时允许 clean 缺失回退 raw
  fail_on_warnings: false
  min_instruction_length: 10
  min_answer_length: 20
  max_answer_length: 6000

design_questions:
  min_evidence_refs: 2            # 同时作为 design_generator.require_min_evidence 的来源
  require_layer_coverage: true

artifacts:
  qa_clean_jsonl: "data/intermediate/clean/qa_clean.jsonl"
  design_clean_jsonl: "data/intermediate/clean/design_clean.jsonl"
```

---

## 8. 交付物（最终应能展示的“加分点”）

- 可训练主干：`data/intermediate/clean/*_clean.jsonl` + `*_sft.jsonl`（clean 导出）
- 可审计 rejected：包含明确 `error.code`、定位信息与简短摘要
- 可回归报告：pass_rate、失败类型分布、按 scenario 的统计、长度分布与 evidence 覆盖分布
- 设计解释：为什么 trace 产生但不训练输出（与 `ExportStep` 策略一致）
