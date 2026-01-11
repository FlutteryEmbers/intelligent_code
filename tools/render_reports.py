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


def _label(chinese: str, english: str) -> str:
    return chinese if USE_CHINESE else english


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


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
    def custom_autopct(pct):
        # Hide percentage on the chart if it's less than 3% to avoid clutter
        return f'{pct:.1f}%' if pct > 3 else ''

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


def _plot_bar(title: str, labels: list[str], values: list[float], out_path: Path, y_label: str = "") -> None:
    # User requested Pie chart instead of Bar chart
    _plot_pie(title, labels, values, out_path)


def _plot_ratio_bar(title: str, labels: list[str], ratios: list[float], out_path: Path) -> None:
    # User requested Pie chart instead of Bar chart
    _plot_pie(title, labels, ratios, out_path)

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


def _plot_coverage(scope: str, data: dict, output_dir: Path) -> None:
    bucket_map = {
        "high": _label("高频", "High"),
        "mid": _label("中等", "Mid"),
        "hard": _label("困难", "Hard"),
    }
    module_map = {
        "single": _label("单模块", "Single"),
        "multi": _label("多模块", "Multi"),
    }
    polarity_map = {
        "positive": _label("正向", "Positive"),
        "negative": _label("负向", "Negative"),
    }
    intent_map = {
        "how_to": _label("操作", "How-to"),
        "config": _label("配置", "Config"),
        "flow": _label("流程", "Flow"),
        "auth": _label("鉴权", "Auth"),
        "error": _label("异常", "Error"),
        "deploy": _label("部署", "Deploy"),
        "impact": _label("变更影响", "Impact"),
        "perf": _label("性能", "Performance"),
        "consistency": _label("一致性", "Consistency"),
        "compatibility": _label("兼容", "Compatibility"),
        "edge": _label("边界", "Edge"),
        "unknown": _label("未知", "Unknown"),
    }
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
            keys = ["high", "mid", "hard"]
            labels = _translate_labels(keys, bucket_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 难度桶",
                f"{scope.upper()} Coverage - Bucket",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        elif label == "intent":
            keys = list(intent_map.keys())
            labels = _translate_labels(keys, intent_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 意图",
                f"{scope.upper()} Coverage - Intent",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        elif label == "module_span":
            keys = ["single", "multi"]
            labels = _translate_labels(keys, module_map)
            ratio_labels = labels
            title = _label(
                f"{scope.upper()} 覆盖分布 - 模块跨度",
                f"{scope.upper()} Coverage - Module Span",
            )
            count_values = _align_counts(counts, keys)
            ratio_values = _align_counts(ratios, keys)
        else:
            keys = ["positive", "negative"]
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


def _plot_retrieval(report: dict, scope: str, output_dir: Path) -> None:
    if not report:
        return
    labels = []
    values = []
    if scope == "qa":
        mapping = [
            ("symbol_evidence_used", _label("证据命中", "Symbol Evidence")),
            ("vector_used", _label("向量检索", "Vector Search")),
            ("vector_filtered", _label("阈值过滤", "Filtered by Score")),
            ("vector_fallback_used", _label("回退使用", "Fallback Used")),
            ("vector_empty", _label("向量空召回", "Vector Empty")),
            ("symbol_only_failures", _label("仅证据失败", "Symbol-only Failures")),
            ("call_chain_expanded", _label("调用链扩展", "Call-chain Expanded")),
        ]
    else:
        mapping = [
            ("scored_non_empty", _label("关键词命中", "Keyword Hit")),
            ("fallback_used", _label("候选回退", "Fallback Used")),
            ("candidates_empty", _label("候选为空", "No Candidates")),
            ("call_chain_expanded", _label("调用链扩展", "Call-chain Expanded")),
        ]

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
    args = parser.parse_args()

    config_path = _resolve_path(REPO_ROOT, args.config)
    cfg = _load_config(config_path)

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
            _plot_coverage("qa", qa_data, coverage_dir)
        if design_data:
            _plot_coverage("design", design_data, coverage_dir)

        errors = []
        if qa_clean_path:
            qa_samples = _read_jsonl(_resolve_path(REPO_ROOT, qa_clean_path))
            if qa_samples:
                qa_actual = _compute_distribution(qa_samples)
                for key in (
                    "bucket_distribution",
                    "intent_distribution",
                    "module_span_distribution",
                    "polarity_distribution",
                ):
                    errors.extend(_compare_counts("qa", qa_data, qa_actual, key))
        if design_clean_path:
            design_samples = _read_jsonl(_resolve_path(REPO_ROOT, design_clean_path))
            if design_samples:
                design_actual = _compute_distribution(design_samples)
                for key in (
                    "bucket_distribution",
                    "intent_distribution",
                    "module_span_distribution",
                    "polarity_distribution",
                ):
                    errors.extend(_compare_counts("design", design_data, design_actual, key))

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
        _plot_retrieval(qa_retrieval, "qa", retrieval_dir)

    design_retrieval = _read_json(reports_path / "design_retrieval_report.json")
    if design_retrieval:
        _plot_retrieval(design_retrieval, "design", retrieval_dir)

    dedup_report = _read_json(reports_path / "dedup_mapping.json")
    if dedup_report:
        _plot_dedup(dedup_report, dedup_dir)

    question_type_report = _read_json(reports_path / "question_type_report.json")
    if question_type_report:
        _plot_question_type(question_type_report, coverage_dir)

    print(f"Rendered reports to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
