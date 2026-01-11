# 修复提案: QA question evidence refs
>
> 日期: 2026-01-11
> Trace 来源: docs/logs/2026-01-11_qa_question_generation_issue_trace_report.md

## Step 1: 摘要与命名 (Summary & Naming)

- **修复摘要**: QA question evidence refs
- **建议文件名**: fix-qa-question-evidence-refs-2026-01-11.md
- **说明**: 规则要求输出到 docs/patchs，但当前约束为“Log Only”，因此本提案写入 docs/logs。

## Step 2: 业务逻辑审计 (Business Logic Audit)

- **业务影响自查**:
  - 将 evidence_refs 字段缺失视为“缺证据”并在 gate 模式拒绝，符合“证据必须由模型显式输出”的要求。
  - report 模式允许自动补齐并打标，不改变 gate 语义，也不影响正式产出。
  - Prompt 增强只加强字段完整性，不削弱问题生成的业务语义。
- **原则检查**:
  - 单一职责：校验归校验、补齐归补齐，职责更清晰。
  - 最小权限：仅在 report 模式容错，不越权进入 gate。
- **判定**: 通过。

## Step 3: 方案 A - 最佳实践修复 (Primary Solution)

**核心思路**: 把“字段缺失”当成 evidence_refs 缺失处理；gate 模式拒绝，report 模式补齐并打标；同时在 prompt 中提供可复制 evidence_refs 模板块并强调 source_hash。

**涉及文件**:
- `src/engine/generators/qa_rule/question_generator.py`
- `configs/prompts/qa_rule/gen_q_user.txt`
- `configs/prompts/qa_rule/coverage_gen_q_user.txt`
- `docs/schemas/generation_models.md`（若需同步字段说明）

**伪代码 / Diff**:
```diff
--- a/src/engine/generators/qa_rule/question_generator.py
+++ b/src/engine/generators/qa_rule/question_generator.py
@@
-    if not q_data.get('evidence_refs'):
-        if gate_mode != 'gate':
-            q_data['evidence_refs'] = [default_ref]
-            q_data['evidence_autofill'] = True
+    missing_fields = _has_missing_evidence_fields(q_data.get('evidence_refs'))
+    if not q_data.get('evidence_refs') or missing_fields:
+        if gate_mode != 'gate':
+            q_data['evidence_refs'] = [default_ref]
+            q_data['evidence_autofill'] = True
+        else:
+            # keep empty/invalid; let validation reject
+            q_data['evidence_refs'] = []
```

```diff
--- a/configs/prompts/qa_rule/gen_q_user.txt
+++ b/configs/prompts/qa_rule/gen_q_user.txt
@@
-每个问题的 evidence_refs 必须从提供的信息中精确复制。
+每个问题的 evidence_refs 必须逐字段完整复制（包含 source_hash）。
+建议直接复制以下模板块：
+{
+  "symbol_id": "{symbol_id}",
+  "file_path": "{file_path}",
+  "start_line": {start_line},
+  "end_line": {end_line},
+  "source_hash": "{source_hash}"
+}
```

**影响范围**:
- QA 问题生成与质量门禁（QuestionGenerator → Validation）。
- 需要重点回归：问题生成成功率、warnings 统计、gate/report 行为一致性。

