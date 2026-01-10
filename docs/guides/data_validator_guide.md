# Data Validator & Visualization Guide

本模块 (`data_validator/`) 负责对数据生成的各个阶段进行可视化分析，并生成最终的图表报告。它不参与数据生成，而是作为“观测者”帮助我们理解数据分布。

## 📂 模块结构

*   **`render_reports.py`**: 核心脚本，读取 `assets/data/reports` 下的 JSON 统计文件，渲染为图表。
*   **`results/`** (或 `assets/visualizations/`): 图表输出目录。

## 🚀 运行指南

该脚本通常在数据生成流水线（`main.py`）结束后手动运行，或者作为 CI/CD 的一部分。

**CMD**:
```bash
python data_validator/render_reports.py
```

执行成功后，控制台会提示报告输出路径。

## 📈 可视化图表说明

生成的图表默认保存在 `assets/visualizations/` 目录下，包含以下几个维度：

### 1. 覆盖率分布 (Coverage)
*   **QA Difficulty Distribution (Pie Chart)**: 此图展示了 QA 样本的难度分布（Recall, Analyses, Reasoning）。
    *   *优化点*: 如果某些类别占比 < 3%，仅在图例中显示，图表中不显示文字，避免重叠。
*   **Intent Distribution**: 问题的意图类型分布（如 explain, usage, error_handling）。

### 2. 质量统计 (Quality)
*   **Generation Success Rate**: 各个 Pipeline 步骤（Parse, Method Understanding, QA Generation）的成功率。
*   **Quality Gate Pass Rate**: 最终样本通过质量门禁的比例。

### 3. 数据流水线 (Pipeline)
*   **Parsing Details**: 展示代码解析阶段的详细统计，例如解析了多少类、方法，失败了多少文件。

## 🧩 常见定制

如果需要调整图表样式（例如颜色、字体、图例位置），请修改 `render_reports.py` 中的 `_plot_pie` 或 `_plot_bar` 方法。

*   **中文字体支持**: 脚本内置了 Microsoft YaHei (Windows) 和 SimHei 的回退机制。
*   **0% 数据处理**: 脚本会自动将样本数为 0 的类别渲染为极细的切片（0.5%），并在图例中显示实际数值，以保证图例的完整性。
