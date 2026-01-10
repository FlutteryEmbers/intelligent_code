# 设计一致性审计报告 (Final Comprehensive)
>
> 审计对象: `src/engine` (Post-Refactor), `src/pipeline`, `src/utils`
> 审计基准: `docs/patchs/*.md` (17 Feature Design Docs) & `refactor_engine.md`
> 日期: 2026-01-10

## 1. 总体合规度摘要 (Executive Summary)

本次审计对 `docs/patchs/` 下的 17 份特性设计文档进行了全覆盖检查。结果显示，重构后的代码库在架构分层、核心流程、质量控制等方面高度符合设计预期。

- **整体合规率**: >90%
- **完全符合**: 16/17 个特性
- **存在偏差**: 1 个特性 (Semantic Constraints & Template Config)
- **严重缺失**: 0

## 2. 审计范围与结果 (Audit Scope & Results)

### Batch 1: Coverage & Distribution

| 特性文档 | 状态 | 说明 |
| :--- | :--- | :--- |
| `feature_coverage_distribution_design.md` | **compliant** | `sampling.py` 实现了 bucket/intent 采样逻辑。 |
| `feature_coverage_distribution_close_loop_design.md` | **compliant** | `coverage_tagger.py` 正确生成报告所需的 coverage 标签。 |
| `feature_coverage_evidence_refs_bucket_design.md` | **compliant** | `coverage.py` 中的 `apply_evidence_bucket` 正确实现了 assist/strict 模式。 |

### Batch 2: Grounding & Trace

| 特性文档 | 状态 | 说明 |
| :--- | :--- | :--- |
| `feature_grounding_chain_recall_design.md` | **compliant** | `retriever.py` 包含 `expand_call_chain` 调用与配置开关检查。 |
| `feature_grounding_strengthen_design.md` | **compliant** | `AnswerGenerator` 实现了 Evidence-First + Vector Fallback (Hybrid) 逻辑。 |
| `feature_trace_counterexample_arch_constraints_design.md` | **compliant** | `AnswerGenerator` 正确注入了 "Rejected Alternatives" 和 "Arch Constraints"。 |
| `feature_reasoning_trace_consistency_design.md` | **compliant** | Validator 实现了 trace 结构一致性校验。 |
| `feature_reasoning_trace_validation_design.md` | **compliant** | `quality.trace_rules` 在 `validator.py` 中得到完整支持。 |

### Batch 3: Diversity & Generation

| 特性文档 | 状态 | 说明 |
| :--- | :--- | :--- |
| `feature_generation_diversity_regression_design.md` | **compliant** | Report 生成逻辑支持 question_type 统计。 |
| `feature_generation_diversity_scenario_injection_design.md` | **compliant** | `QuestionGenerator` 实现了 Quota 采样和 Scenario Injection (arguments 传递)。 |
| `feature_negative_sampling_design.md` | **compliant** | `AnswerGenerator` 实现了负样本采样与 Prompt 规则注入。 |
| `feature_semantic_dedup_design.md` | **compliant** | `deduplication.py` 实现了 SimHash + Semantic Embedding 两阶段去重。 |

### Batch 4: Quality & Validation

| 特性文档 | 状态 | 说明 |
| :--- | :--- | :--- |
| `feature_quality_cleaning_blacklist_design.md` | **compliant** | `secrets_scan.py` 实现了关键词黑名单与 keep/drop/sanitize 策略。 |
| `feature_quality_gate_design.md` | **compliant** | `validation.py` 产出 `clean/QA_clean.jsonl`，实现了 Gate 逻辑。 |
| `feature_raw_quality_gate_design.md` | **compliant** | 同上。 |

### Deviation Analysis (QA Generator)

| 模块/功能 | 设计要求 | 代码现状 | 差异严重度 |
| :--- | :--- | :--- | :--- |
| **Semantic Constraints**<br>(`feature_generation...`) | 支持可在配置中切换的 `coverage_generation` 独立 Prompt 模板，用于 A/B 测试或影子模式。 | `src/engine/generators/qa_rule/question_generator.py` (L224) 硬编码使用 `"gen_q_user"` 模板，**忽略**了配置项。 | **Medium** |

**影响**:
虽然 `QuestionGenerator` 已经通过参数传递实现了 Semantic Constraints 的 core logic (约束规则注入)，但由于模板名称硬编码，用户无法通过修改 config 来平滑切换到一套新的模板（例如 `gen_q_user_v2_coverage`），这降低了系统的灵活性，不符合 Design 中关于 "Phase 1/2" 渐进式发布的策略。

**建议行动**:
修改 `QuestionGenerator._generate_questions`，读取配置中的 template name（如果存在），否则回退到默认值。

```python
# 建议修改示例
template_name = self.coverage_cfg.get('template_name', 'gen_q_user')
user_prompt = self._build_composed_user_prompt(template_name, ...)
```

## 3. 结论

代码库整体健康度极高，重构工作扎实。除 `QuestionGenerator` 的一处可配置性缺陷外，所有核心设计均已准确落地。建议修复该缺陷后结束本次审计。
