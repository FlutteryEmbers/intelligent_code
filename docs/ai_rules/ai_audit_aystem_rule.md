# Role: 资深软件架构师 & 设计模式专家 (GoF & Enterprise Integration Patterns Specialist)

# Context
我正在对一个 **“自动化训练集生成系统 (Automated Training Set Generation System)”** 进行架构复盘。该系统的核心目标是从源码/文档中提取数据，经过清洗和格式化，最终生成用于 LLM 微调（Fine-tuning）的数据集（如 JSONL, Parquet）。

# Goal
请分析我的当前代码库，撰写一份**《系统设计模式与架构分析报告》**。你需要识别代码中现有的设计模式，并评估其合理性；同时指出哪些地方可以通过引入设计模式来解耦或优化。

# Analysis Focus (Domain Specific)
在分析时，请重点关注以下“训练集生成”场景常见的模式：
1. **Pipeline / Chain of Responsibility**: 数据处理链路（读取 -> 清洗 -> 格式化 -> 落盘）。
2. **Strategy Pattern**: 针对不同源文件（.py, .java, .md）的不同解析策略。
3. **Template Method**: 定义数据处理的标准骨架，让子类实现具体的解析逻辑。
4. **Adapter / Facade**: 对接不同的大模型 API 或外部数据源。
5. **Generator / Iterator**: 处理大规模数据流时的内存优化。

# Task
请在 `docs/architecture/design_pattern_analysis.md` 中生成报告，包含以下章节：

## 1. 核心架构风格 (Architectural Style)
- 简述系统目前是倾向于 **管道过滤器 (Pipe & Filter)** 风格，还是 **批处理 (Batch Processing)** 风格？
- 用 Mermaid `graph LR` 画出数据流动的高层架构图。

## 2. 现有设计模式识别 (Identified Patterns)
> 请列出代码中实际体现出的设计模式（显式或隐式）：
- **模式名称**: (例如: Strategy Pattern)
- **代码位置**: (引用具体的类名或接口，如 `ParserStrategy`)
- **作用分析**: 该模式如何帮助解决了训练集生成的具体问题（例如：隔离了 Python 和 Java 的解析差异）。
- **Mermaid 类图**: 简单的 `classDiagram` 展示该模式的结构。

## 3. "代码坏味道"与重构建议 (Missed Opportunities)
> 这是最关键的部分。请指出代码中逻辑耦合过重的地方，并建议引入何种设计模式进行改进。
- **痛点描述**: (例如：`DataProcessor` 类中充满了 `if file_type == 'python'` 的巨大 switch-case 语句)
- **建议模式**: (例如：建议重构为 Factory + Strategy 模式)
- **预期收益**: (例如：新增一种语言支持时，无需修改主流程，符合开闭原则 OCP)。

## 4. 总结与评分
- **可扩展性评分 (1-10)**: 增加新的数据源或输出格式的难度。
- **一句话总结**: 对当前架构成熟度的评价。

---
**Constraints**:
- **Analysis Only**: 严禁修改代码。
- **Professionalism**: 使用标准的软件工程术语（如：关注点分离、依赖倒置）。