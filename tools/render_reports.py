from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Missing PyYAML. Install via `pip install -r requirements.txt`.") from exc

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
except ImportError as exc:
    raise SystemExit("Missing matplotlib. Install via `pip install -r requirements.txt`.") from exc


REPO_ROOT = Path(__file__).resolve().parents[1]
CHINESE_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
]


def _configure_fonts() -> bool:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in CHINESE_FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


USE_CHINESE = _configure_fonts()
CHART_STYLE = "pie"
SMALL_SLICE_THRESHOLD = 0.03


def _label(chinese: str, english: str) -> str:
    return chinese if USE_CHINESE else english


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    if not path.exists():
        return [], 0
    items = []
    invalid_lines = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
    return items, invalid_lines


def _plot_pie(title: str, labels: list[str], values: list[float], out_path: Path) -> None:
    if not labels or not values:
        return
    
    # Calculate percentages for ALL items
    total = sum(values)
    if total == 0:
        return
        
    legend_labels = []
    for l, v in zip(labels, values):
        pct = (v / total) * 100
        # If value is integer-like (count), show count. If float (ratio), just show pct
        if all(isinstance(x, int) or (isinstance(x, float) and x.is_integer()) for x in values):
            legend_labels.append(f"{l}: {int(v)} ({pct:.1f}%)")
        else:
            legend_labels.append(f"{l} ({pct:.1f}%)")

    # Use a small epsilon for 0 values so they render as a sliver
    epsilon = total * 0.005 if total > 0 else 1.0
    
    plot_values = []
    plot_colors = []
    original_values = []
    
    colors = plt.get_cmap("tab20c")(range(len(labels)))
    
    for i, v in enumerate(values):
        original_values.append(v)
        plot_values.append(max(v, epsilon)) # Force at least epsilon for rendering
        plot_colors.append(colors[i])
            
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Define autopct to hide label for small/zero items
    threshold = SMALL_SLICE_THRESHOLD * 100

    def custom_autopct(pct):
        # Hide percentage on the chart if it's less than threshold to avoid clutter
        return f"{pct:.1f}%" if pct > threshold else ""

    wedges, texts, autotexts = ax.pie(
        plot_values, 
        labels=None, # Hide labels on the wheel itself to prevent overlap. Relies on Legend.
        autopct=custom_autopct, 
        startangle=140, 
        colors=plot_colors,
        pctdistance=0.85,
        textprops=dict(color="black")
    )
    
    # Post-process: ensure hidden text is actually hidden (handled by custom_autopct mostly)
    # But we double check the original values for 0s just in case
    for i, val in enumerate(original_values):
        if val == 0:
            autotexts[i].set_text("")
    
    # Draw circle for donut style
    centre_circle = plt.Circle((0,0),0.70,fc='white')
    fig.gca().add_artist(centre_circle)
    
    ax.set_title(title, pad=20)
    ax.axis('equal')
    
    # Create legend handles explicitly to match original values logic
    import matplotlib.patches as mpatches
    handles = []
    for i, label in enumerate(legend_labels):
        handles.append(mpatches.Patch(color=colors[i], label=label))

    # Legend
    ax.legend(handles=handles,
          loc="center left",
          bbox_to_anchor=(1, 0, 0.5, 1))

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_bar_impl(title: str, labels: list[str], values: list[float], out_path: Path, y_label: str = "") -> None:
    if not labels or not values:
        return
    fig, ax = plt.subplots(figsize=(12, 7))
    x = list(range(len(labels)))
    ax.bar(x, values, color="#4c78a8")
    ax.set_title(title, pad=20)
    if y_label:
        ax.set_ylabel(y_label)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_by_style(
    style: str, title: str, labels: list[str], values: list[float], out_path: Path, y_label: str = ""
) -> None:
    if style == "pie":
        _plot_pie(title, labels, values, out_path)
    else:
        _plot_bar_impl(title, labels, values, out_path, y_label)


def _plot_bar(title: str, labels: list[str], values: list[float], out_path: Path, y_label: str = "") -> None:
    _plot_by_style(CHART_STYLE, title, labels, values, out_path, y_label)


def _plot_ratio_bar(title: str, labels: list[str], ratios: list[float], out_path: Path) -> None:
    _plot_by_style(CHART_STYLE, title, labels, ratios, out_path)

def _plot_ratio_comparison(
    title: str,
    labels: list[str],
    actual: list[float],
    target: list[float],
    out_path: Path,
) -> None:
    if not labels or not actual or not target:
        return
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = list(range(len(labels)))
    width = 0.38
    ax.bar([i - width / 2 for i in x], actual, width, color="#5a9b6a", label=_label("实际", "Actual"))
    ax.bar([i + width / 2 for i in x], target, width, color="#e3a64f", label=_label("目标", "Target"))
    ax.set_title(title)
    ax.set_ylabel(_label("比例", "Ratio"))
    ax.set_xlabel(_label("类别", "Category"))
    ax.set_ylim(0, 1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30)
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_quality(report: dict, prefix: str, output_dir: Path) -> None:
    stats = report.get("validation_stats", {})
    total = stats.get("total", 0)
    passed = stats.get("passed", 0)
    failed = stats.get("failed", 0)
    _plot_bar(
        _label(f"{prefix.upper()} 质量概览", f"{prefix.upper()} Quality Overview"),
        [_label("总量", "Total"), _label("通过", "Passed"), _label("失败", "Failed")],
        [total, passed, failed],
        output_dir / f"{prefix}_quality_overview.png",
        _label("数量", "Count"),
    )

    top_failures = report.get("top_failures", [])
    if top_failures:
        labels = [item.get("error", "") for item in top_failures]
        values = [item.get("count", 0) for item in top_failures]
        _plot_bar(
            _label(f"{prefix.upper()} 失败原因 TOP", f"{prefix.upper()} Top Failures"),
            labels,
            values,
            output_dir / f"{prefix}_top_failures.png",
            _label("数量", "Count"),
        )

    top_warnings = report.get("top_warnings", [])
    if top_warnings:
        labels = [item.get("warning", "") for item in top_warnings]
        values = [item.get("count", 0) for item in top_warnings]
        _plot_bar(
            _label(f"{prefix.upper()} 告警原因 TOP", f"{prefix.upper()} Top Warnings"),
            labels,
            values,
            output_dir / f"{prefix}_top_warnings.png",
            _label("数量", "Count"),
        )


def _translate_labels(labels: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping.get(label, label) for label in labels]


def _align_counts(counts: dict, keys: list[str]) -> list[float]:
    return [counts.get(key, 0) for key in keys]

def _merge_keys(primary: list[str], secondary: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for key in primary + secondary:
        if key not in seen:
            merged.append(key)
            seen.add(key)
    return merged


def _merge_config_and_actual(config_keys: list[str], counts: dict, ratios: dict) -> list[str]:
    keys = list(config_keys) if config_keys else []
    for key in list(counts.keys()) + list(ratios.keys()):
        if key not in keys:
            keys.append(key)
    return keys


def _plot_coverage(
    scope: str, data: dict, output_dir: Path, coverage_keys: dict, label_map: dict
) -> None:
    bucket_map = label_map.get("bucket", {})
    if not isinstance(bucket_map, dict):
        bucket_map = {}
    module_map = label_map.get("module_span", {})
    if not isinstance(module_map, dict):
        module_map = {}
    polarity_map = label_map.get("polarity", {})
    if not isinstance(polarity_map, dict):
        polarity_map = {}
    intent_map = label_map.get("intent", {})
    if not isinstance(intent_map, dict):
        intent_map = {}
    for key, label in [
        ("bucket_distribution", "bucket"),
        ("intent_distribution", "intent"),
        ("module_span_distribution", "module_span"),
        ("polarity_distribution", "polarity"),
    ]:
        dist = data.get(key, {})
        counts = dist.get("counts", {})
        ratios = dist.get("ratios", {})
        if label == "bucket":
            config_keys = coverage_keys.get("bucket", [])
            keys = _merge_config_and_actual(config_keys, counts, ratios)
            labels = _translate_labels(keys, bucket_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 难度桶",
                f"{scope.upper()} Coverage - Bucket",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        elif label == "intent":
            config_keys = coverage_keys.get("intent", [])
            keys = _merge_config_and_actual(config_keys, counts, ratios)
            labels = _translate_labels(keys, intent_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 意图",
                f"{scope.upper()} Coverage - Intent",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        elif label == "module_span":
            config_keys = coverage_keys.get("module_span", [])
            keys = _merge_config_and_actual(config_keys, counts, ratios)
            labels = _translate_labels(keys, module_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 模块跨度",
                f"{scope.upper()} Coverage - Module Span",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        else:
            config_keys = coverage_keys.get("polarity", [])
            keys = _merge_config_and_actual(config_keys, counts, ratios)
            labels = _translate_labels(keys, polarity_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 正负样本",
                f"{scope.upper()} Coverage - Polarity",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        if counts is not None:
            _plot_bar(
                _label(f"{title}（计数）", f"{title} (Count)"),
                labels,
                count_values,
                output_dir / f"{scope}_coverage_{label}_counts.png",
                _label("数量", "Count"),
            )
        if ratios is not None:
            _plot_ratio_bar(
                _label(f"{title}（比例）", f"{title} (Ratio)"),
                ratio_labels,
                ratio_values,
                output_dir / f"{scope}_coverage_{label}_ratios.png",
            )


def _plot_parsing(report: dict, output_dir: Path) -> None:
    _plot_bar(
        _label("解析结果概览", "Parsing Overview"),
        [_label("文件总数", "Total Files"), _label("解析成功", "Parsed"), _label("解析失败", "Failed")],
        [
            report.get("total_files", 0),
            report.get("parsed_files", 0),
            report.get("failed_files", 0),
        ],
        output_dir / "parsing_files.png",
        _label("数量", "Count"),
    )
    symbols = report.get("symbols_by_type", {})
    if symbols:
        _plot_bar(
            _label("符号类型分布", "Symbols by Type"),
            list(symbols.keys()),
            list(symbols.values()),
            output_dir / "parsing_symbols_by_type.png",
            _label("数量", "Count"),
        )


def _build_retrieval_mapping(
    scope: str, retrieval_keys: dict, retrieval_labels: dict, report: dict
) -> list[tuple[str, str]]:
    keys = retrieval_keys.get(scope, [])
    if not keys:
        keys = list(report.keys())
    labels = retrieval_labels.get(scope, {})
    mapping = []
    for key in keys:
        label = labels.get(key, key)
        if isinstance(label, dict):
            label = label.get("zh") if USE_CHINESE else label.get("en", key)
        mapping.append((key, label))
    return mapping


def _plot_retrieval(
    report: dict,
    scope: str,
    output_dir: Path,
    retrieval_keys: dict,
    retrieval_labels: dict,
) -> None:
    if not report:
        return
    labels = []
    values = []
    mapping = _build_retrieval_mapping(scope, retrieval_keys, retrieval_labels, report)

    for key, label in mapping:
        if key in report:
            labels.append(label)
            values.append(report.get(key, 0))

    if labels:
        _plot_bar(
            _label(f"{scope.upper()} 检索统计", f"{scope.upper()} Retrieval Stats"),
            labels,
            values,
            output_dir / f"{scope}_retrieval_stats.png",
            _label("数量", "Count"),
        )


def _plot_dedup(report: dict, output_dir: Path) -> None:
    if not report:
        return

    def _plot_block(label: str, data: dict, filename: str) -> None:
        total = data.get("total_input", 0)
        kept = data.get("total_kept", 0)
        dropped = data.get("total_dropped", 0)
        title = label
        if data.get("skipped"):
            reason = data.get("reason", "skipped")
            title = _label(f"{label}（跳过：{reason}）", f"{label} (skipped: {reason})")
        _plot_bar(
            title,
            [_label("总量", "Total"), _label("保留", "Kept"), _label("删除", "Dropped")],
            [total, kept, dropped],
            output_dir / filename,
            _label("数量", "Count"),
        )

    _plot_block(_label("去重概览（SimHash）", "Dedup Overview (SimHash)"), report, "dedup_simhash_overview.png")

    semantic = report.get("semantic")
    if isinstance(semantic, dict):
        _plot_block(
            _label("去重概览（语义）", "Dedup Overview (Semantic)"),
            semantic,
            "dedup_semantic_overview.png",
        )


def _plot_question_type(report: dict, output_dir: Path) -> None:
    if not report:
        return
    for scope in ("qa", "design"):
        data = report.get(scope, {})
        dist = data.get("distribution", {})
        counts = dist.get("counts", {})
        ratios = dist.get("ratios", {})
        targets = data.get("targets", {})
        keys = _merge_keys(list(targets.keys()), list(counts.keys()))
        if not keys:
            keys = list(ratios.keys())
        if counts:
            _plot_bar(
                _label(f"{scope.upper()} 问题类型分布", f"{scope.upper()} Question Types"),
                keys,
                _align_counts(counts, keys),
                output_dir / f"{scope}_question_type_counts.png",
                _label("数量", "Count"),
            )
        if ratios:
            _plot_ratio_bar(
                _label(f"{scope.upper()} 问题类型比例", f"{scope.upper()} Question Type Ratios"),
                keys,
                _align_counts(ratios, keys),
                output_dir / f"{scope}_question_type_ratios.png",
            )
        if targets:
            _plot_ratio_comparison(
                _label(
                    f"{scope.upper()} 问题类型比例（实际 vs 目标）",
                    f"{scope.upper()} Question Types (Actual vs Target)",
                ),
                keys,
                _align_counts(ratios, keys),
                _align_counts(targets, keys),
                output_dir / f"{scope}_question_type_targets.png",
            )


def _resolve_path(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _compute_distribution(samples: list[dict]) -> dict:
    bucket_counts = {}
    intent_counts = {}
    module_counts = {}
    polarity_counts = {}

    for sample in samples:
        coverage = sample.get("quality", {}).get("coverage", {})
        bucket = coverage.get("bucket") or "high"
        intent = coverage.get("intent") or "unknown"
        module_span = coverage.get("module_span") or "unknown"
        polarity = coverage.get("polarity") or "positive"

        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        module_counts[module_span] = module_counts.get(module_span, 0) + 1
        polarity_counts[polarity] = polarity_counts.get(polarity, 0) + 1

    def ratios(counts: dict) -> dict:
        total = sum(counts.values())
        if total == 0:
            return {}
        return {key: round(value / total, 4) for key, value in counts.items()}

    return {
        "bucket_distribution": {"counts": bucket_counts, "ratios": ratios(bucket_counts)},
        "intent_distribution": {"counts": intent_counts, "ratios": ratios(intent_counts)},
        "module_span_distribution": {"counts": module_counts, "ratios": ratios(module_counts)},
        "polarity_distribution": {"counts": polarity_counts, "ratios": ratios(polarity_counts)},
    }


def _compare_counts(scope: str, expected: dict, actual: dict, key: str) -> list[str]:
    exp_counts = expected.get(key, {}).get("counts", {})
    act_counts = actual.get(key, {}).get("counts", {})
    errors = []
    if exp_counts != act_counts:
        errors.append(
            f"{scope} {key} counts mismatch: expected={exp_counts} actual={act_counts}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Render report charts from pipeline reports")
    parser.add_argument("--config", default="configs/launch.yaml", help="Path to launch.yaml")
    parser.add_argument("--reports-dir", default=None, help="Override reports directory")
    parser.add_argument("--output-dir", default="tools/results", help="Output directory for charts")
    parser.add_argument("--chart-style", default="pie", choices=["bar", "pie"], help="Chart style")
    parser.add_argument(
        "--coverage-keys",
        default="configs/types/coverage_keys.yaml",
        help="Coverage key ordering config",
    )
    parser.add_argument(
        "--viz-config",
        default="configs/types/report_visualization.yaml",
        help="Visualization label and mapping config",
    )
    parser.add_argument(
        "--small-slice-threshold",
        type=float,
        default=0.03,
        help="Hide pie labels below this ratio",
    )
    args = parser.parse_args()

    global CHART_STYLE
    global SMALL_SLICE_THRESHOLD
    CHART_STYLE = args.chart_style
    SMALL_SLICE_THRESHOLD = args.small_slice_threshold

    config_path = _resolve_path(REPO_ROOT, args.config)
    cfg = _load_config(config_path)
    coverage_cfg = _load_config(_resolve_path(REPO_ROOT, args.coverage_keys))
    qa_coverage_keys = coverage_cfg.get("qa", {})
    design_coverage_keys = coverage_cfg.get("design", {})
    viz_cfg = _load_config(_resolve_path(REPO_ROOT, args.viz_config))
    label_map = viz_cfg.get("label_map", {})
    retrieval_keys = viz_cfg.get("retrieval_keys", {})
    retrieval_labels = viz_cfg.get("retrieval_labels", {})

    reports_dir = args.reports_dir
    if not reports_dir:
        reports_dir = cfg.get("output", {}).get("reports_dir", "data/reports")
    reports_path = _resolve_path(REPO_ROOT, reports_dir)

    artifacts = cfg.get("artifacts", {})
    coverage_path = artifacts.get("coverage_report_json") or str(reports_path / "coverage_report.json")
    qa_clean_path = artifacts.get("qa_clean_jsonl")
    design_clean_path = artifacts.get("design_clean_jsonl")
    qa_quality_path = str(reports_path / "qa_quality.json")
    design_quality_path = str(reports_path / "design_quality.json")
    parsing_path = str(reports_path / "parsing_report.json")

    output_dir = _resolve_path(REPO_ROOT, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_dir = output_dir / "coverage"
    quality_dir = output_dir / "quality"
    parsing_dir = output_dir / "parsing"
    retrieval_dir = output_dir / "retrieval"
    dedup_dir = output_dir / "dedup"
    for path in (coverage_dir, quality_dir, parsing_dir, retrieval_dir, dedup_dir):
        path.mkdir(parents=True, exist_ok=True)

    coverage_report = _read_json(_resolve_path(REPO_ROOT, coverage_path))
    if coverage_report:
        qa_data = coverage_report.get("qa", {})
        design_data = coverage_report.get("design", {})
        if qa_data:
            _plot_coverage("qa", qa_data, coverage_dir, qa_coverage_keys, label_map)
        if design_data:
            _plot_coverage("design", design_data, coverage_dir, design_coverage_keys, label_map)

        errors = []
        if qa_clean_path:
            qa_samples, qa_invalid = _read_jsonl(_resolve_path(REPO_ROOT, qa_clean_path))
            if qa_samples:
                qa_actual = _compute_distribution(qa_samples)
                for key in (
                    "bucket_distribution",
                    "intent_distribution",
                    "module_span_distribution",
                    "polarity_distribution",
                ):
                    errors.extend(_compare_counts("qa", qa_data, qa_actual, key))
            if qa_invalid:
                print(f"[WARN] {qa_invalid} invalid JSONL lines ignored: {qa_clean_path}")
        if design_clean_path:
            design_samples, design_invalid = _read_jsonl(_resolve_path(REPO_ROOT, design_clean_path))
            if design_samples:
                design_actual = _compute_distribution(design_samples)
                for key in (
                    "bucket_distribution",
                    "intent_distribution",
                    "module_span_distribution",
                    "polarity_distribution",
                ):
                    errors.extend(_compare_counts("design", design_data, design_actual, key))
            if design_invalid:
                print(f"[WARN] {design_invalid} invalid JSONL lines ignored: {design_clean_path}")

        if errors:
            for item in errors:
                print(f"[ERROR] {item}")
            raise SystemExit("Coverage report does not match dataset distributions.")

    qa_quality = _read_json(_resolve_path(REPO_ROOT, qa_quality_path))
    if qa_quality:
        _plot_quality(qa_quality, "qa", quality_dir)

    design_quality = _read_json(_resolve_path(REPO_ROOT, design_quality_path))
    if design_quality:
        _plot_quality(design_quality, "design", quality_dir)

    parsing_report = _read_json(_resolve_path(REPO_ROOT, parsing_path))
    if parsing_report:
        _plot_parsing(parsing_report, parsing_dir)

    qa_retrieval = _read_json(reports_path / "qa_retrieval_report.json")
    if qa_retrieval:
        _plot_retrieval(qa_retrieval, "qa", retrieval_dir, retrieval_keys, retrieval_labels)

    design_retrieval = _read_json(reports_path / "design_retrieval_report.json")
    if design_retrieval:
        _plot_retrieval(design_retrieval, "design", retrieval_dir, retrieval_keys, retrieval_labels)

    dedup_report = _read_json(reports_path / "dedup_mapping.json")
    if dedup_report:
        _plot_dedup(dedup_report, dedup_dir)

    question_type_report = _read_json(reports_path / "question_type_report.json")
    if question_type_report:
        _plot_question_type(question_type_report, coverage_dir)

    print("[INFO] Render summary:")
    print(f"[INFO] reports_dir={reports_dir}")
    print(f"[INFO] output_dir={output_dir}")
    print(f"[INFO] chart_style={args.chart_style}")
    print(f"[INFO] coverage_keys={args.coverage_keys}")
    print(f"[INFO] viz_config={args.viz_config}")
    print(f"Rendered reports to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
