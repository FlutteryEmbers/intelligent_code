"""
架构设计生成器测试脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.engine.design_generator import DesignGenerator, BUILT_IN_REQUIREMENTS
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_design_generation():
    """测试架构设计生成器"""
    print("\n" + "=" * 70)
    print(" 架构设计方案生成器测试")
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
    
    # 显示内置需求
    print(f"\n[1/4] 内置需求列表 ({len(BUILT_IN_REQUIREMENTS)} 个):")
    for req in BUILT_IN_REQUIREMENTS:
        print(f"  - [{req.id}] {req.goal[:60]}...")
    
    # 初始化生成器
    print("\n[2/4] 初始化架构设计生成器...")
    
    config = Config()
    
    # 测试环境：限制生成数量
    config._config['design_generator'] = config._config.get('design_generator', {})
    config._config['design_generator']['max_samples'] = 2  # 仅生成 2 个样本用于测试
    config._config['design_generator']['top_k_context'] = 4
    
    generator = DesignGenerator(config=config)
    
    print(f"   ✓ Top-K 上下文数量: {generator.top_k_context}")
    print(f"   ✓ 最大上下文字符数: {generator.max_context_chars}")
    print(f"   ✓ 最大生成数量: {generator.max_samples}")
    
    # 生成样本
    print("\n[3/4] 开始生成架构设计方案...")
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
    print("\n[4/4] 展示生成的样本...")
    
    if samples:
        # 显示第一个样本
        sample = samples[0]
        
        print("\n" + "-" * 70)
        print(" 示例样本 #1")
        print("-" * 70)
        print(f"\n场景: {sample.scenario}")
        print(f"\n需求/指令:\n{sample.instruction}")
        print(f"\n上下文 (前200字符):\n{sample.context[:200]}...")
        
        print(f"\n设计方案 (前800字符):")
        print(sample.answer[:800] + "...")
        
        if sample.thought:
            print(f"\n推理过程:")
            print(f"  - 观察数量: {len(sample.thought.observations)}")
            print(f"  - 推断数量: {len(sample.thought.inferences)}")
            print(f"  - 证据引用: {len(sample.thought.evidence_refs)}")
            print(f"  - 假设数量: {len(sample.thought.assumptions)}")
            
            if sample.thought.observations:
                print(f"\n  关键观察 (前3条):")
                for i, obs in enumerate(sample.thought.observations[:3], 1):
                    print(f"    {i}. {obs[:80]}...")
            
            if sample.thought.inferences:
                print(f"\n  设计推断 (前3条):")
                for i, inf in enumerate(sample.thought.inferences[:3], 1):
                    print(f"    {i}. {inf[:80]}...")
            
            if sample.thought.evidence_refs:
                print(f"\n  证据引用:")
                for ref in sample.thought.evidence_refs[:3]:
                    print(f"    - {ref.symbol_id}")
                    print(f"      文件: {ref.file_path}")
                    print(f"      行范围: {ref.start_line}-{ref.end_line}")
            
            if sample.thought.assumptions:
                print(f"\n  设计假设 (前2条):")
                for i, assume in enumerate(sample.thought.assumptions[:2], 1):
                    print(f"    {i}. {assume[:80]}...")
        
        print(f"\nRepo Commit: {sample.repo_commit}")
        
        if sample.quality:
            print(f"\n质量标记: {sample.quality}")
        
        print("\n" + "-" * 70)
    
    # 打印摘要
    generator.print_summary()
    
    # 检查输出文件
    print("\n验证输出文件:")
    
    output_files = [
        generator.requirements_path,
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
    print("  1. 查看生成的需求: data/intermediate/requirements.jsonl")
    print("  2. 查看设计方案: data/intermediate/design_raw.jsonl")
    print("  3. 查看失败样本: data/intermediate/design_rejected.jsonl")
    print("  4. 调整配置并重新生成更多样本")
    
    return True


def main():
    """主测试函数"""
    try:
        success = test_design_generation()
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
