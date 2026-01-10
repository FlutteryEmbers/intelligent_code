# Reports & Operational Artifacts

这些 JSON 文件用于记录 Pipeline 的执行情况、数据质量与分布统计。

## QualityReport
> 文件: `*_validation_report.json`
> 生成者: `src/utils/data/validator.py`

Validator 运行后的总体验收报告。
*   `validation_stats`: 包含 total, passed, failed, pass_rate。
*   `top_failures`: 出现频率最高的错误类型。
*   `top_warnings`: 出现频率最高的警告类型。
*   `trace_summary`: 推理轨迹 (Reasoning Trace) 的质量统计。

## CoverageReport
> 文件: `data/reports/coverage_report.json`

由 `CoverageSamplerStep` 生成。
*   统计 QA/Design 的分布情况（Bucket, Intent, Module Span）。
*   包含 `targets` (目标比例) 和 `deficits` (缺失数量)。

## QuestionTypeReport
> 文件: `data/reports/question_type_report.json`

由 `QuestionTypeReportStep` 生成。
*   记录问题类型的分布。
*   包含 `regression.warnings`，当分布严重偏离目标时发出警告。

## ParsingReport
> 文件: `data/reports/parsing_report.json`

解析阶段的体检报告。
*   `repo_commit`: 解析的代码版本。
*   `total_files` / `parsed_files` / `failed_files`: 解析覆盖率。
*   `errors`: 详细的解析失败原因列表。

## PipelineSummary
> 文件: `data/reports/pipeline_summary.json`

由 `Orchestrator` 生成的最终汇总。
*   列出所有执行的步骤 (`steps`)。
*   列出所有产出的文件工件 (`output_files`)。

## DedupMapping
> 文件: `data/reports/dedup_mapping.json`

去重日志。
*   记录 `kept` (保留) 和 `dropped` (丢弃) 的样本数量。
*   记录具体的重复对 (`pairs`)。
