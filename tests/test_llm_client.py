"""
LLM Client 测试脚本 - 独立测试文件
"""
from pathlib import Path
from src.engine import LLMClient
from src.utils import get_logger

logger = get_logger(__name__)


def main():
    """测试 LLMClient 的主要功能"""
    print("\n" + "=" * 70)
    print(" LLM Client 功能测试")
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
    
    # 3. 构建测试提示词
    print("\n[3/5] 准备测试提示词...")
    
    # 检查当前使用的模型
    if "coder" in client.model.lower() and "3b" in client.model.lower():
        print(f"   ⚠️  检测到小型 Coder 模型：{client.model}")
        print(f"   提示：如遇到失败，建议切换到通用模型")
        print(f"   执行：export OLLAMA_MODEL=qwen2.5:7b")
        print()
    
    system_prompt = """你是一个 Java 代码分析专家。
根据给定的代码片段，生成一个训练样本用于 Qwen2.5 模型微调。
样本应该包含清晰的问题、相关上下文和详细的答案。"""
    
    user_prompt = """请分析以下 Java 代码并生成训练样本：

```java
public class Calculator {
    /**
     * 计算两个整数的和
     */
    public int add(int a, int b) {
        return a + b;
    }
    
    /**
     * 计算两个整数的差
     */
    public int subtract(int a, int b) {
        return a - b;
    }
}
```

请生成一个 QA 类型的训练样本：
- instruction: "这个 Calculator 类提供了哪些数学运算功能？"
- context: 包含完整的类代码
- thought: 包含你的观察和推理过程
- answer: 详细描述类的功能
"""
    
    print("   ✓ 提示词准备完成")
    
    # 4. 生成训练样本
    print("\n[4/5] 生成训练样本（可能需要 10-30 秒）...")
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
            print(f"     • Inferences: {len(sample.thought.inferences)} 条")
            print(f"     • Evidence Refs: {len(sample.thought.evidence_refs)} 条")
        
    except ValueError as e:
        print(f"   ✗ 生成失败: {e}")
        print(f"\n   拒绝样本已记录到: {client.rejected_log_path}")
        
        # 提供详细的故障排查建议
        print(f"\n   ⚠️  故障排查建议：")
        print(f"   1. 查看拒绝样本详情：")
        print(f"      cat {client.rejected_log_path}")
        print(f"\n   2. 如果模型返回空的代码块或非 JSON 输出，建议切换模型：")
        print(f"      ollama pull qwen2.5:7b")
        print(f"      export OLLAMA_MODEL=qwen2.5:7b")
        print(f"      python test_llm_client_improved.py")
        print(f"\n   3. 其他可用模型：")
        print(f"      - qwen2.5:14b (更好，需要更多内存)")
        print(f"      - llama3.1:8b (替代方案)")
        print(f"      - qwen2.5:7b-instruct-q4_K_M (量化版本，节省内存)")
        print(f"\n   详细说明：docs/MODEL_RECOMMENDATIONS.md")
        
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
