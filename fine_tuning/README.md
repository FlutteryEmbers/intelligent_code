# 训练模块

本目录包含基于项目生成的 SFT 数据（`../data/final/*_sft.jsonl`）对 Qwen2.5-Coder 系列模型进行微调的完整训练脚本。

## 🎯 功能特性

- ✅ LoRA/QLoRA 微调支持
- ✅ 独立的依赖管理（不影响数据生成环境）
- ✅ 多种模型尺寸配置（1.5B / 3B / 7B）
- ✅ 自动评测和人工评测支持
- ✅ Chat template 自动处理
- ✅ 训练监控（wandb/tensorboard）

## 📋 快速开始

### 1. 安装依赖

```bash
# 进入训练模块目录
cd fine_tuning

# 安装训练依赖（建议使用独立环境）
pip install -r requirements.txt
```

### 2. 下载底座模型

```bash
# 使用快捷方式下载（推荐）
python download_model.py --model 1.5b
python download_model.py --model 3b
python download_model.py --model 7b

# 或手动下载
huggingface-cli download Qwen/Qwen2.5-Coder-1.5B-Instruct \
  --local-dir ../models/Qwen2.5-Coder-1.5B-Instruct \
  --local-dir-use-symlinks False
```

### 3. 启动训练

```bash
# LoRA 训练（推荐先用 1.5B 快速验证）
python train.py configs/lora_1.5b.yaml

# 使用更大模型
python train.py configs/lora_3b.yaml

# QLoRA 训练（显存受限时）
python train.py configs/qlora_7b.yaml
```

### 4. 评测模型

```bash
# 使用默认路径评测（最简单）
python eval.py

# 或自定义路径
python eval.py \
  --checkpoint ../checkpoints/lora-qwen2.5-coder-3b \
  --data ../data/final/test_sft.jsonl

# 快速测试（只评测10个样本）
python eval.py --max-samples 10
```

**默认路径说明**：
- Checkpoint: `../checkpoints/lora-qwen2.5-coder-1.5b`
- 验证数据: `../data/final/val_sft.jsonl`
- 输出结果: `../data/eval_results.jsonl`

## 📁 目录结构

```
fine_tuning/
├── README.md                # 本文档
├── requirements.txt         # 训练依赖
│
├── train.py                 # ← 训练入口（用户工具）
├── eval.py                  # ← 评测入口
├── download_model.py        # ← 模型下载
│
├── configs/                 # 训练配置
│   ├── lora_1.5b.yaml
│   ├── lora_3b.yaml
│   └── qlora_7b.yaml
│
├── libs/                    # 核心库（可复用模块）
│   ├── __init__.py
│   ├── trainer.py           # 训练逻辑
│   ├── data_loader.py       # 数据加载
│   └── utils.py             # 工具函数
│
└── evaluation/              # 评测模块（可选）
    ├── evaluator.py
    ├── metrics.py
    └── human_eval.py
```

## ⚙️ 配置说明

训练配置文件位于 `configs/` 目录，主要参数：

- `base_model`: 底座模型路径
- `output_dir`: 训练输出路径
- `train_data` / `val_data`: 训练/验证数据路径
- `lora_r` / `lora_alpha`: LoRA 参数
- `max_seq_length`: 最大序列长度（代码上下文较长，建议 4096+）
- `learning_rate`: 学习率（LoRA 建议 1e-4）
- `num_train_epochs`: 训练轮数

详细配置说明见 `../docs/guides/training_guide.md`

## 🔧 常见问题

### Q: 显存不足怎么办？

A: 尝试以下方案：
1. 使用 QLoRA（4bit 量化）
2. 减小 `per_device_train_batch_size`，增大 `gradient_accumulation_steps`
3. 使用更小的模型（1.5B → 3B）
4. 减小 `max_seq_length`

### Q: 训练速度太慢？

A: 优化建议：
1. 启用 flash attention（如果 GPU 支持）
2. 增大 batch size（如果显存允许）
3. 使用多卡训练（修改脚本添加 `accelerate launch`）

### Q: 如何查看训练进度？

A: 三种方式：
1. wandb：在配置中启用 `report_to: wandb`
2. tensorboard：`tensorboard --logdir ../checkpoints/xxx`
3. 日志文件：`tail -f ../logs/training.log`

## 📖 相关文档

- [微调技术方案](../docs/guides/fine_tuning_guide.md) - 模型选型和训练策略
- [训练操作手册](../docs/guides/training_guide.md) - 详细操作步骤
- [评测指南](../docs/guides/evaluation_guide.md) - 如何评测模型效果

## 🤝 贡献

训练模块独立维护，欢迎提交 PR 改进训练脚本和配置。
