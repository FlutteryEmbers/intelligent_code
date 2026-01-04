"""
改进的测试脚本 - 使用更好的提示词
"""
from pathlib import Path
from src.engine import LLMClient
from src.utils import get_logger

logger = get_logger(__name__)


def main():
    """测试 LLMClient 的主要功能"""
    print("\n" + "=" * 70)
    print(" LLM Client 功能测试（改进版）")
    print("=" * 70)
    
    # 1. 初始化客户端
    print("\n[1/5] 初始化 LLMClient...")
    try:
        client = LLMClient()
        print(f"   ✓ Base URL: {client.base_url}")
        print(f"   ✓ Model: {client.model}")
        print(f"   ✓ Temperature: {client.temperature}")
        print(f"   ✓ Max Tokens: {client.max_tokens}")
        print(f"   ✓ Timeout: {client.timeout}s")
    except Exception as e:
        print(f"   ✗ 初始化失败: {e}")
        return False
    
    # 2. 测试连接
    print("\n[2/5] 测试 Ollama 连接...")
    if not client.test_connection():
        print("   ✗ 连接失败")
        print("   提示：请确保 Ollama 服务已启动（ollama serve）")
        print(f"   提示：尝试访问 {client.base_url.replace('/v1', '')}")
        return False
    print("   ✓ 连接成功")
    
    # 3. 构建改进的测试提示词
    print("\n[3/5] 准备测试提示词...")
    
    # 更简洁明确的系统提示
    system_prompt = """你是一个训练数据生成助手。
你的任务是根据给定的代码生成 JSON 格式的训练样本。"""
    
    # 更简洁的用户提示
    user_prompt = """给定代码：
public class Calculator {
    public int add(int a, int b) { return a + b; }
    public int subtract(int a, int b) { return a - b; }
}

生成训练样本，要求：
- instruction: "这个类提供了什么功能？"
- context: 包含上述代码
- thought.observations: ["包含 add 方法", "包含 subtract 方法"]
- thought.inferences: ["这是一个计算器类", "提供基本数学运算"]
- answer: 详细描述功能"""
    
    print("   ✓ 提示词准备完成")
    
    # 4. 生成训练样本
    print("\n[4/5] 生成训练样本（可能需要 10-30 秒）...")
    print("   提示：如果使用 coder 模型失败，建议切换到通用模型")
    print("   执行：export OLLAMA_MODEL=qwen2.5:7b")
    
    try:
        sample = client.generate_training_sample(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            scenario="qa_rule",
            repo_commit="test_commit_abc123"
        )
        
        print("   ✓ 样本生成成功！")
        print(f"\n   样本详情：")
        print(f"   - Sample ID: {sample.sample_id}")
        print(f"   - Scenario: {sample.scenario}")
        print(f"   - Instruction: {sample.instruction}")
        print(f"   - Context 长度: {len(sample.context)} 字符")
        print(f"   - Answer 长度: {len(sample.answer)} 字符")
        
        if not sample.thought.is_empty():
            print(f"   - Thought:")
            print(f"     • Observations: {len(sample.thought.observations)} 条")
            if sample.thought.observations:
                for obs in sample.thought.observations[:2]:
                    print(f"       - {obs}")
            print(f"     • Inferences: {len(sample.thought.inferences)} 条")
            if sample.thought.inferences:
                for inf in sample.thought.inferences[:2]:
                    print(f"       - {inf}")
        
    except ValueError as e:
        print(f"   ✗ 生成失败: {e}")
        print(f"\n   拒绝样本已记录到: {client.rejected_log_path}")
        print(f"\n   ⚠️ 建议尝试：")
        print(f"   1. 使用更大的模型：ollama pull qwen2.5:7b")
        print(f"   2. 设置环境变量：export OLLAMA_MODEL=qwen2.5:7b")
        print(f"   3. 或使用其他模型：export OLLAMA_MODEL=llama3.1:8b")
        return False
    except Exception as e:
        print(f"   ✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. 保存测试结果
    print("\n[5/5] 保存测试结果...")
    try:
        output_path = Path("data/intermediate/test_llm_sample.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(sample.model_dump_json(indent=2))
        
        print(f"   ✓ 样本已保存到: {output_path}")
        
        # 显示样本内容预览
        print(f"\n   样本内容预览：")
        print(f"   " + "-" * 66)
        print(f"   Instruction: {sample.instruction}")
        print(f"   " + "-" * 66)
        print(f"   Answer (前 200 字符): ")
        print(f"   {sample.answer[:200]}...")
        print(f"   " + "-" * 66)
        
    except Exception as e:
        print(f"   ✗ 保存失败: {e}")
        return False
    
    # 测试完成
    print("\n" + "=" * 70)
    print(" ✓ 所有测试通过！")
    print("=" * 70)
    print(f"\n提示：")
    print(f"  - 查看完整样本：{output_path}")
    print(f"  - 查看拒绝样本（如有）：{client.rejected_log_path}")
    print()
    
    return True


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
