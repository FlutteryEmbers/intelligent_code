# 项目安装和运行指南

## 前置要求

1. **Python 3.10+**
   - 下载：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"

2. **Ollama**（可选，用于 LLM 生成）
   - 下载：https://ollama.ai/
   - 安装后运行：`ollama pull qwen2.5:latest`

## 安装步骤

### 1. 安装 Python 依赖

```bash
# 进入项目目录
cd d:\Codes\intelligent_code_generator

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
# source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置项目

编辑 `configs/pipeline.yaml`：

```yaml
repo:
  path: "D:/path/to/your/java/repo"  # 修改为实际 Java 项目路径
```

或使用环境变量：

```bash
# Windows PowerShell
$env:REPO_PATH = "D:\path\to\your\java\repo"
$env:OLLAMA_BASE_URL = "http://localhost:11434"

# Windows CMD
set REPO_PATH=D:\path\to\your\java\repo
set OLLAMA_BASE_URL=http://localhost:11434

# Linux/Mac
export REPO_PATH="/path/to/your/java/repo"
export OLLAMA_BASE_URL="http://localhost:11434"
```

### 3. 运行演示

```bash
python main.py
```

成功运行后会看到：
- 配置信息展示
- 数据模型示例
- 解析器说明
- 自动创建输出目录

## 验证安装

### 检查 Python 版本

```bash
python --version
# 应输出：Python 3.10.x 或更高
```

### 检查依赖安装

```bash
pip list
```

应包含以下核心包：
- tree-sitter
- pydantic
- pyyaml
- langchain-openai
- ollama

### 测试配置加载

```bash
python -c "from src.utils import config; print(config.ollama_model)"
```

应输出：`qwen2.5:latest`

## 目录结构验证

运行 `main.py` 后会自动创建以下目录：

```
data/
├── raw/
│   ├── extracted/
│   └── repo_meta/
├── intermediate/
├── final/
└── reports/
logs/
```

## 常见问题

### Q1: 找不到模块 'tree_sitter'

**解决**：
```bash
pip install tree-sitter tree-sitter-java
```

### Q2: 配置文件找不到

**解决**：确保 `configs/pipeline.yaml` 存在，或运行：
```bash
# 检查文件
dir configs\pipeline.yaml  # Windows
ls configs/pipeline.yaml   # Linux/Mac
```

### Q3: Ollama 连接失败

**解决**：
1. 确保 Ollama 已启动：`ollama serve`
2. 检查端口：http://localhost:11434
3. 测试连接：`curl http://localhost:11434`

### Q4: Python 命令不存在

**解决**：
1. 检查 Python 是否安装：`where python` (Windows) 或 `which python` (Linux/Mac)
2. 确保已添加到 PATH
3. 可能需要使用 `python3` 或 `py` 命令

## 下一步

骨架搭建完成后，可以开始实现：

1. **JavaParser** - 具体的 Java 代码解析器
2. **SampleGenerator** - 训练样本生成引擎
3. **QualityChecker** - 质量评估模块

参考 `README.md` 了解更多信息。
