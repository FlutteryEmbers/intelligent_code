# 修复摘要
问题核心：render reports visualization

- 计划文件名: `docs/patchs/fix-render-reports-visualization-2026-01-11.md`
- 实际输出位置: `docs/logs/fix-render-reports-visualization-2026-01-11.md`
- 参考 Trace: `docs/logs/2026-01-11_render_reports_visualization_design_audit_report.md`
- 日期: 2026-01-11

## 2. 业务逻辑审计 (Business Logic Audit)

**判定**: 有风险

**说明**:
- 本次修复主要改善“图表的可读性与可信度”，不直接影响生成数据或业务流程，整体符合单一职责原则。
- 但引入更明确的缺失/异常提示或“分布一致性校验”的增强逻辑，可能导致之前“静默成功”的场景被显式标为失败；对依赖当前宽松行为的流程有潜在影响，需要确认是否允许提升失败可见性。
- 将业务口径（keys/labels/retrieval 显示）迁移到业务配置文件后，配置维护权重会上升，需要明确配置变更的责任人。

## 3. 方案 A - 最佳实践修复 (Primary Solution)

### 涉及文件
- `tools/render_reports.py`
- `configs/types/coverage_keys.yaml`
- `configs/types/report_visualization.yaml`
- `docs/features/05_observability/report_visualization.md`

### 伪代码 / Diff

```diff
--- a/tools/render_reports.py
+++ b/tools/render_reports.py
@@
-def _plot_bar(...):
-    # User requested Pie chart instead of Bar chart
-    _plot_pie(...)
+def _plot_bar(...):
+    # Use chart_style from CLI (default pie)
+    _plot_by_style(chart_style, ...)

-def _plot_ratio_bar(...):
-    _plot_pie(...)
+def _plot_ratio_bar(...):
+    _plot_by_style(chart_style, ...)

+def _plot_by_style(style, title, labels, values, out_path, y_label=""):
+    # style: pie | bar
+    if style == "pie":
+        _plot_pie(...)
+    else:
+        _plot_bar_impl(...)
@@
-def _plot_coverage(scope: str, data: dict, output_dir: Path) -> None:
+def _plot_coverage(scope: str, data: dict, output_dir: Path, coverage_keys: dict, label_map: dict) -> None:
@@
-    keys = ["high", "mid", "hard"]
+    keys = coverage_keys.get("bucket", ["high", "mid", "hard"])
@@
-    keys = list(intent_map.keys())
+    keys = coverage_keys.get("intent", list(intent_map.keys()))
@@
-    keys = ["single", "multi"]
+    keys = coverage_keys.get("module_span", ["single", "multi"])
@@
-    keys = ["positive", "negative"]
+    keys = coverage_keys.get("polarity", ["positive", "negative"])
@@
-def _read_jsonl(...):
-    except json.JSONDecodeError:
-        continue
+def _read_jsonl(...):
+    invalid_lines = 0
+    ...
+    except json.JSONDecodeError:
+        invalid_lines += 1
+    return items, invalid_lines
@@
-def main():
-    parser.add_argument("--output-dir", ...)
+def main():
+    parser.add_argument("--output-dir", ...)
+    parser.add_argument("--chart-style", default="pie", choices=["bar","pie"])
+    parser.add_argument("--coverage-keys", default="configs/types/coverage_keys.yaml")
+    parser.add_argument("--viz-config", default="configs/types/report_visualization.yaml")
+    parser.add_argument("--small-slice-threshold", type=float, default=0.03)
+    parser.add_argument("--warn-missing", action="store_true", default=True)
@@
-    cfg = _load_config(config_path)
+    cfg = _load_config(config_path)
+    coverage_cfg = _load_config(_resolve_path(REPO_ROOT, args.coverage_keys))
+    qa_coverage_keys = coverage_cfg.get("qa", {})
+    design_coverage_keys = coverage_cfg.get("design", {})
+    viz_cfg = _load_config(_resolve_path(REPO_ROOT, args.viz_config))
+    label_map = viz_cfg.get("label_map", {})
+    retrieval_keys = viz_cfg.get("retrieval_keys", {})
+    retrieval_labels = viz_cfg.get("retrieval_labels", {})
@@
-    bucket_map = {...}
-    module_map = {...}
-    polarity_map = {...}
-    intent_map = {...}
+    bucket_map = label_map.get("bucket", {...})
+    module_map = label_map.get("module_span", {...})
+    polarity_map = label_map.get("polarity", {...})
+    intent_map = label_map.get("intent", {...})
@@
-    _plot_coverage("qa", qa_data, coverage_dir)
+    _plot_coverage("qa", qa_data, coverage_dir, qa_coverage_keys, label_map)
@@
-    _plot_coverage("design", design_data, coverage_dir)
+    _plot_coverage("design", design_data, coverage_dir, design_coverage_keys, label_map)
@@
-def _plot_retrieval(report: dict, scope: str, output_dir: Path) -> None:
+def _plot_retrieval(report: dict, scope: str, output_dir: Path) -> None:
@@
-    if scope == "qa":
-        mapping = [ ... ]
-    else:
-        mapping = [ ... ]
+    mapping = build_mapping_from_config(scope, retrieval_keys, retrieval_labels)
@@
-print("[INFO] Render summary:")
+print("[INFO] Render summary:")
 print(f"[INFO] reports_dir={reports_dir}")
 print(f"[INFO] output_dir={output_dir}")
 print(f"[INFO] used_reports=... missing_reports=...")
+print(f"[INFO] chart_style={args.chart_style}")
+print(f"[INFO] coverage_keys={args.coverage_keys}")
+print(f"[INFO] viz_config={args.viz_config}")
```

```diff
--- a/configs/types/coverage_keys.yaml
+++ b/configs/types/coverage_keys.yaml
+qa:
+  bucket: [high, mid, hard, unknown]
+  intent: [how_to, config, flow, auth, error, deploy, impact, perf, consistency, compatibility, edge, unknown]
+  module_span: [single, multi, unknown]
+  polarity: [positive, negative]
+design:
+  bucket: [high, mid, hard, unknown]
+  intent: [architecture, integration, consistency, error_handling, performance, security, maintenance, unknown]
+  module_span: [single, multi, unknown]
+  polarity: [positive, negative]
```

```diff
--- a/configs/types/report_visualization.yaml
+++ b/configs/types/report_visualization.yaml
+label_map:
+  bucket:
+    high: "高频"
+    mid: "中等"
+    hard: "困难"
+    unknown: "未知"
+  intent:
+    how_to: "操作"
+    config: "配置"
+    flow: "流程"
+    auth: "鉴权"
+    error: "异常"
+    deploy: "部署"
+    impact: "变更影响"
+    perf: "性能"
+    consistency: "一致性"
+    compatibility: "兼容"
+    edge: "边界"
+    unknown: "未知"
+    architecture: "架构"
+    integration: "集成"
+    error_handling: "错误处理"
+    performance: "性能"
+    security: "安全"
+    maintenance: "维护"
+  module_span:
+    single: "单模块"
+    multi: "多模块"
+    unknown: "未知"
+  polarity:
+    positive: "正向"
+    negative: "负向"
+retrieval_keys:
+  qa: [symbol_evidence_used, vector_used, vector_filtered, vector_fallback_used, vector_empty, symbol_only_failures, call_chain_expanded]
+  design: [scored_non_empty, fallback_used, candidates_empty, call_chain_expanded]
+retrieval_labels:
+  qa:
+    symbol_evidence_used: "证据命中"
+    vector_used: "向量检索"
+    vector_filtered: "阈值过滤"
+    vector_fallback_used: "回退使用"
+    vector_empty: "向量空召回"
+    symbol_only_failures: "仅证据失败"
+    call_chain_expanded: "调用链扩展"
+  design:
+    scored_non_empty: "关键词命中"
+    fallback_used: "候选回退"
+    candidates_empty: "候选为空"
+    call_chain_expanded: "调用链扩展"
```

### 影响范围
- 报表输出准确性（覆盖分布、问题类型分布）
- 视觉可读性（图表类型由 CLI 控制）
- 运行提示与异常可见性
- 业务口径一致性（keys/labels/retrieval 由业务配置文件统一维护）

重点测试：
- 覆盖报告含未知类别时图表是否仍完整
- CLI 设置为 bar/pie 时图表类型是否正确
- 缺失报表/JSONL 非法行是否给出可操作提示
- `--viz-config` 指向自定义文件时是否覆盖默认映射
- `--coverage-keys` 指向自定义文件时是否正确生效

