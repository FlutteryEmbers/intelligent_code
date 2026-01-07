#!/usr/bin/env python3
"""
LoRA/QLoRA 微调训练脚本

Usage:
    python train.py configs/lora_1.5b.yaml
    python train.py configs/qlora_7b.yaml
"""
import sys
from pathlib import Path

# 获取脚本所在目录（fine_tuning目录）
script_dir = Path(__file__).parent

# 确保可以导入 libs 模块
sys.path.insert(0, str(script_dir))

from libs.trainer import train


def main():
    if len(sys.argv) < 2:
        print("Usage: python train.py <config_file>")
        print("\nAvailable configs:")
        config_dir = script_dir / "configs"
        if config_dir.exists():
            for config_file in sorted(config_dir.glob("*.yaml")):
                # 显示相对于当前目录的路径
                try:
                    rel_path = config_file.relative_to(Path.cwd())
                except ValueError:
                    rel_path = config_file
                print(f"  - {rel_path}")
        sys.exit(1)
    
    config_path = Path(sys.argv[1])
    
    # 如果是相对路径，尝试相对于当前目录解析
    if not config_path.is_absolute():
        # 首先尝试相对于当前工作目录
        if not config_path.exists():
            # 如果不存在，尝试相对于脚本目录
            alt_path = script_dir / config_path
            if alt_path.exists():
                config_path = alt_path
    
    # 检查配置文件是否存在
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        print(f"\nTried paths:")
        print(f"  - {Path.cwd() / sys.argv[1]}")
        print(f"  - {script_dir / sys.argv[1]}")
        sys.exit(1)
    
    print(f"Starting training with config: {config_path}")
    train(config_path)


if __name__ == "__main__":
    main()
