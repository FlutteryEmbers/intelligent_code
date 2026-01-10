# Fine-Tuning Module Guide

本模块提供了基于 LoRA/QLoRA 的大模型微调与评估的一站式工具链，支持 SFT（有监督微调）和基于 ROUGE/BLEU 的自动化评估。

## 📂 模块结构 (`fine_tuning/`)

*   **`train.py`**: 微调主入口，基于 HuggingFace Trainer。
*   **`eval.py`**: 评估主入口，支持基座模型对比、指标计算与定性报告生成。
*   **`download_model.py`**: 辅助工具，用于下载 HF 模型权重。
*   **`configs/*.yaml`**: 训练配置文件（包含 QLoRA 参数、路径配置等）。
*   **`libs/`**: 核心逻辑封装（Dataset Loading, Trainer 扩展等）。

## ⚙️ 环境准备

建议为训练单独创建一个环境，避免与主 Pipeline 冲突：

```bash
conda create -n finetune python=3.10
conda activate finetune
pip install torch transformers peft datasets accelerate bitsandbytes rouge_score nltk pyyaml
# Windows 用户请注意安装适合的 Torch CUDA 版本
```

## 🚀 运行指南

### 1. 下载模型权重 (Optional)

如果本地没有底座模型，可以使用脚本下载（默认下载到 `fine_tuning/models/`）：

```bash
python fine_tuning/download_model.py --model_name Qwen/Qwen2.5-Coder-1.5B-Instruct
```

### 2. 启动微调 (Training)

使用 `configs/` 下的 YAML 配置文件启动训练。

**CMD 示例**:
```bash
# Windows / Linux
python fine_tuning/train.py fine_tuning/configs/lora_1.5b.yaml
```

**配置文件说明 (`lora_1.5b.yaml`)**:
```yaml
model_name: "Qwen/Qwen2.5-Coder-1.5B-Instruct"  # 底座模型路径
data_path: "../assets/data/final"                 # 训练数据路径
output_dir: "./checkpoints/lora-1.5b"             # Checkpoint 保存路径
training:
  per_device_train_batch_size: 2
  gradient_accumulation_steps: 8
  learning_rate: 2e-4
  num_train_epochs: 3
  use_lora: true                                  # 开启 LoRA
  use_qlora: true                                 # 开启 4-bit 量化
```

### 3. 模型评估 (Evaluation)

评估脚本会自动加载训练好的 Adapter，并与基座模型进行对比。

**CMD 示例**:
```bash
# 自动读取 config 中的 output_dir 寻找 checkpoint
python fine_tuning/eval.py --config fine_tuning/configs/lora_1.5b.yaml --compare-base --report
```

**参数说明**:
- `--config`: 指定训练时的配置文件（用于自动定位 checkpoint 和数据）。
- `--compare-base`: 是否同时运行基座模型（Base Model）进行对比。
- `--report`: 生成 Markdown 格式的详细报告（包含 Metrics 表格和定性 Case）。

**输出结果**:
- 评估报告: `assets/eval_fine_tuning_report.md`
- 详细结果: `assets/data/eval_results.jsonl`

## 📊 常见问题

- **Windows 多进程报错**: 如果遇到 `BrokenPipeError`，请在 yaml 中设置 `dataloader_num_workers: 0`。
- **显存不足 (OOM)**:
    - 减小 `per_device_train_batch_size` (e.g., 1)。
    - 增加 `gradient_accumulation_steps` (e.g., 16)。
    - 确保 `use_qlora: true` 以启用 4-bit 量化。
