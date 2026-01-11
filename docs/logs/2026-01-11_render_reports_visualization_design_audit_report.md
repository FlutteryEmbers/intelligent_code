# 设计一致性审计报告
> 问题总结: 审计 `tools/render_reports.py` 是否满足“清晰可视化报表”的需求，并给出改进建议与更合理的提示策略。
> 审计对象: tools/render_reports.py
> 审计基准: docs/features/05_observability/report_visualization.md; docs/schemas/reports.md
> 日期: 2026-01-11

## 1. 总体合规度摘要

- **完全符合**: 40%
- **存在偏差**: 4 个模块
- **严重缺失**: 2 个功能点

## 2. 差异矩阵 (Discrepancy Matrix)

| 模块/功能 | 设计要求 | 代码现状 | 差异严重度 (High/Med/Low) |
| :--- | :--- | :--- | :--- |
| 覆盖分布可视化 | 分布应准确反映所有类别 | 固定 key 列表导致未知/新增类别被遗漏 | High |
| 图表可读性 | 图表一眼看懂，避免信息被掩盖 | 强制饼图 + 小于 3% 直接隐藏标签 | High |
| 数据呈现可信度 | 统计为 0 应真实展示为 0 | 0 值被强制绘制为非零扇区 | High |
| 报表缺失提示 | 缺失输入应明确提示 | 读取失败或 JSONL 无效行直接静默忽略 | Medium |
| 运行提示 | 明确说明使用了哪些报表与输出路径 | 仅输出最终路径，缺少输入概览 | Low |

## 3. 详细审计发现

### 3.1 覆盖分布存在“丢类”风险
- **设计描述**: 报表可视化需要准确反映分布情况（见 `docs/features/05_observability/report_visualization.md`）。
- **代码实现**: `_plot_coverage` 仅使用固定 key 列表生成图表，未包含未知/新增类别。`module_span` 只保留 `single`/`multi`，但 `_compute_distribution` 会生成 `unknown`（`tools/render_reports.py:241-332`, `tools/render_reports.py:477-505`）。
- **主要问题**: 当 `coverage` 中出现 `unknown` 或新增类别时，图表会直接漏掉，导致“看图不等于真实分布”。
- **建议行动**: 用“数据实际 keys + 目标 keys 合并”的方式生成标签；将未识别项归入 `Other` 并明确标注。

### 3.2 饼图强制化降低可读性
- **设计描述**: 图表应“一眼看懂”，适合对比（见 `docs/features/05_observability/report_visualization.md`）。
- **代码实现**: `_plot_bar`/`_plot_ratio_bar` 被改为直接使用饼图（`tools/render_reports.py:150-157`），意图/问题类型分布也随之变成饼图（`tools/render_reports.py:241-332`, `tools/render_reports.py:427-454`）。
- **主要问题**: 类别多时饼图难以比较，且图例过长；`custom_autopct` 对小于 3% 的项直接不显示（`tools/render_reports.py:105-108`），会隐藏真实分布。
- **建议行动**: 提供图表类型开关（bar/pie），对高基数类别默认柱状/水平条形；小比例合并为 `Other` 并在图例中注明阈值。

### 3.3 0 值被可视化为“非零”
- **设计描述**: 图表应可靠表达真实统计。
- **代码实现**: 0 值被用 `epsilon` 强制绘制为扇区（`tools/render_reports.py:89-101`）。
- **主要问题**: 视觉上出现非零扇区，容易造成误判，违背“清晰可信”的基本要求。
- **建议行动**: 对 0 值直接隐藏扇区；如需提示“为 0”，应在图例中显示 `0 (0.0%)`。

### 3.4 缺失/异常输入缺少提示
- **设计描述**: 报表清晰可视化应伴随可解释的输入提示。
- **代码实现**: `_read_json`/`_read_jsonl` 对缺失文件或非法行静默忽略（`tools/render_reports.py:48-67`），主流程也不打印“缺失哪些报表”。
- **主要问题**: 用户可能误以为图表完整，实际是“部分缺失”。
- **建议行动**: 增加缺失文件提示、无效 JSONL 行统计；在最终输出中列出“已加载/缺失”的报表清单。

### 3.5 运行提示信息不足
- **设计描述**: 作为“业务仪表盘”，需要明确告知数据来源与输出（`docs/features/05_observability/report_visualization.md`）。
- **代码实现**: 仅输出 `Rendered reports to ...`（`tools/render_reports.py:619`）。
- **主要问题**: 缺乏“输入 → 输出”链路提示，不利于审计追踪。
- **建议行动**: 输出报表路径摘要、输出目录结构摘要；若启用一致性校验失败，建议提示包含差异摘要与下一步排查建议。
