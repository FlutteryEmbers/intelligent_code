"""
QA 生成器测试脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.engine.qa_generator import QAGenerator
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_qa_generation():
    """测试 QA 生成器"""
    print("\n" + "=" * 70)
    print(" QA 生成器测试")
    print("=" * 70)
    
    # 检查符号文件是否存在
    symbols_path = Path("data/raw/extracted/symbols.jsonl")
    
    if not symbols_path.exists():
        print(f"\n⚠️  符号文件不存在: {symbols_path}")
        print("请先运行 Java 解析器生成符号文件：")
        print("  python tests/test_java_parser.py")
        return False
    
    print(f"✓ 找到符号文件: {symbols_path}")
    
    # 统计符号数量
    with open(symbols_path, 'r', encoding='utf-8') as f:
        symbol_count = sum(1 for line in f if line.strip())
    
    print(f"✓ 符号文件包含 {symbol_count} 个符号")
    
    # 初始化生成器
    print("\n[1/3] 初始化 QA 生成器...")
    
    config = Config()
    
    # 测试环境：限制生成数量
    config._config['qa_generator'] = config._config.get('qa_generator', {})
    config._config['qa_generator']['max_samples'] = 5  # 仅生成 5 个样本用于测试
    config._config['qa_generator']['batch_size'] = 2
    
    generator = QAGenerator(config=config)
    
    print(f"   ✓ 最大上下文字符数: {generator.max_context_chars}")
    print(f"   ✓ 批处理大小: {generator.batch_size}")
    print(f"   ✓ 最大生成数量: {generator.max_samples}")
    
    # 生成样本
    print("\n[2/3] 开始生成 QA 训练样本...")
    print("   （这可能需要几分钟，取决于 LLM 响应速度）")
    
    try:
        samples = generator.generate_from_repo(
            symbols_path=symbols_path,
            repo_commit=None  # 自动推断
        )
        
        print(f"\n   ✓ 成功生成 {len(samples)} 个样本")
        
    except Exception as e:
        print(f"\n   ✗ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 展示结果
    print("\n[3/3] 展示生成的样本...")
    
    if samples:
        # 显示第一个样本
        sample = samples[0]
        
        print("\n" + "-" * 70)
        print(" 示例样本 #1")
        print("-" * 70)
        print(f"\n场景: {sample.scenario}")
        print(f"\n指令/问题:\n{sample.instruction}")
        print(f"\n上下文 (前100字符):\n{sample.context[:100]}...")
        print(f"\n回答:\n{sample.answer[:500]}..." if len(sample.answer) > 500 else f"\n回答:\n{sample.answer}")
        
        if sample.thought:
            print(f"\n推理过程:")
            print(f"  - 观察数量: {len(sample.thought.observations)}")
            print(f"  - 推断数量: {len(sample.thought.inferences)}")
            print(f"  - 证据引用: {len(sample.thought.evidence_refs)}")
            
            if sample.thought.observations:
                print(f"\n  关键观察:")
                for i, obs in enumerate(sample.thought.observations[:3], 1):
                    print(f"    {i}. {obs}")
            
            if sample.thought.evidence_refs:
                print(f"\n  证据引用:")
                for ref in sample.thought.evidence_refs[:2]:
                    print(f"    - {ref.symbol_id}")
                    print(f"      文件: {ref.file_path}")
                    print(f"      行范围: {ref.start_line}-{ref.end_line}")
        
        print(f"\nRepo Commit: {sample.repo_commit}")
        
        if sample.quality:
            print(f"\n质量标记: {sample.quality}")
        
        print("\n" + "-" * 70)
    
    # 打印摘要
    generator.print_summary()
    
    # 检查输出文件
    print("\n验证输出文件:")
    
    output_files = [
        generator.raw_output_path,
        generator.rejected_path
    ]
    
    for file_path in output_files:
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  ✓ {file_path} ({size} bytes)")
        else:
            print(f"  - {file_path} (不存在)")
    
    print("\n" + "=" * 70)
    print(" ✓ 测试完成！")
    print("=" * 70)
    
    print("\n下一步:")
    print("  1. 查看生成的样本: data/intermediate/qa_raw.jsonl")
    print("  2. 查看失败样本: data/intermediate/qa_rejected.jsonl")
    print("  3. 调整配置并重新生成更多样本")
    
    return True


def main():
    """主测试函数"""
    try:
        success = test_qa_generation()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
