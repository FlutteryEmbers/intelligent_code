#!/usr/bin/env python3
"""
模型下载脚本

Usage:
    python download_model.py --model 1.5b              # 下载 Qwen2.5-Coder-1.5B-Instruct
    python download_model.py --model 3b                # 下载 Qwen2.5-Coder-3B-Instruct
    python download_model.py --model Qwen/xxx          # 下载任意HF模型
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path


SUPPORTED_MODELS = {
    "1.5b": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "3b": "Qwen/Qwen2.5-Coder-3B-Instruct",
    "7b": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "14b": "Qwen/Qwen2.5-Coder-14B-Instruct",
}


def download_model(model_name: str, output_dir: Path, use_hf_transfer: bool = True):
    """下载模型"""
    print(f"📥 Downloading model: {model_name}")
    print(f"📂 Output directory: {output_dir}")
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 设置环境变量启用加速下载
    env = os.environ.copy()
    if use_hf_transfer:
        env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
        print("⚡ Using hf_transfer for faster download")
        print("   (install if not available: pip install hf-transfer)")
    
    # 构造下载命令
    cmd = [
        "huggingface-cli",
        "download",
        model_name,
        "--local-dir", str(output_dir),
        "--local-dir-use-symlinks", "False"
    ]
    
    print(f"\n🚀 Running: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, env=env, check=True)
        print(f"\n✅ Model downloaded successfully!")
        print(f"📁 Location: {output_dir}")
        print(f"\n💡 Next step: Edit configs/lora_*.yaml to use this model")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Download failed: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Check your internet connection")
        print("   2. Verify HuggingFace access token if model is gated")
        print("   3. Try: huggingface-cli login")
        return False
    except FileNotFoundError:
        print("\n❌ huggingface-cli not found!")
        print("\n💡 Install with: pip install -U huggingface_hub")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Download Qwen2.5-Coder models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 使用快捷方式下载
  python download_model.py --model 1.5b
  python download_model.py --model 3b
  python download_model.py --model 7b
  
  # 下载完整模型名称
  python download_model.py --model Qwen/Qwen2.5-Coder-1.5B-Instruct
  
  # 自定义输出目录
  python download_model.py --model 1.5b --output-dir /path/to/models
        """
    )
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help=f"Model to download. Shortcuts: {', '.join(SUPPORTED_MODELS.keys())} or full HF model name"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: ./models/<model_name>)"
    )
    parser.add_argument(
        "--no-hf-transfer",
        action="store_true",
        help="Disable hf_transfer acceleration"
    )
    
    args = parser.parse_args()
    
    # 解析模型名称
    if args.model.lower() in SUPPORTED_MODELS:
        model_name = SUPPORTED_MODELS[args.model.lower()]
        default_dir_name = f"Qwen2.5-Coder-{args.model.upper()}-Instruct"
    else:
        model_name = args.model
        default_dir_name = model_name.split("/")[-1]
    
    # 确定输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        # 默认保存到项目根目录的 models/ 目录
        output_dir = script_dir / "models" / default_dir_name
    
    print("=" * 60)
    print(f"Model Download Utility")
    print("=" * 60)
    
    # 下载模型
    success = download_model(
        model_name=model_name,
        output_dir=output_dir,
        use_hf_transfer=not args.no_hf_transfer
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
