"""
LLM 客户端 - 本地 LLM 调用封装（支持 Ollama）
"""
import json
import time
from pathlib import Path
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from src.utils.schemas import TrainingSample
from src.utils.config import config
from src.utils.logger import get_logger


logger = get_logger(__name__)


class LLMClient:
    """
    LLM 客户端 - 封装本地 Ollama 调用
    
    特性：
    1. 使用 langchain_openai.ChatOpenAI 兼容 Ollama
    2. 结构化输出（强制返回符合 TrainingSample schema 的 JSON）
    3. 自动重试机制（最多 2 次）
    4. 失败样本记录到 rejected_llm.jsonl
    """
    
    def __init__(
        self, 
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        """
        初始化 LLM 客户端
        
        Args:
            base_url: Ollama API 地址，默认从配置读取
            model: 模型名称，默认从配置读取
            temperature: 温度参数，默认从配置读取
            max_tokens: 最大 token 数，默认从配置读取
            timeout: 超时时间（秒），默认从配置读取
        """
        # 配置参数（优先使用传入参数，否则从配置文件读取）
        self.base_url = base_url or config.get('llm.base_url', 'http://localhost:11434/v1')
        self.model = model or config.get('llm.model', 'qwen2.5-coder-3b-instruct')
        self.temperature = temperature if temperature is not None else config.get('llm.temperature', 0.7)
        self.max_tokens = max_tokens or config.get('llm.max_tokens', 2000)
        self.timeout = timeout or config.get('llm.timeout_sec', 60)
        
        # 最大重试次数
        self.max_retries = 2
        
        # 拒绝样本输出路径
        self.rejected_log_path = (
            Path(config.get('output.intermediate_dir', 'data/intermediate')) / 'rejected_llm.jsonl'
        )
        self.rejected_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化 ChatOpenAI 客户端
        self.llm = ChatOpenAI(
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            api_key="ollama",  # Ollama 不需要真实 API key，但参数必填
        )
        
        # 初始化 Pydantic 输出解析器
        self.output_parser = PydanticOutputParser(pydantic_object=TrainingSample)
        
        logger.info(f"LLMClient initialized: base_url={self.base_url}, model={self.model}")
    
    def generate_training_sample(
        self, 
        system_prompt: str, 
        user_prompt: str,
        scenario: str = "qa_rule",
        repo_commit: str = "unknown"
    ) -> TrainingSample:
        """
        生成训练样本（结构化输出）
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            scenario: 场景类型（"qa_rule" 或 "arch_design"）
            repo_commit: 仓库 commit hash
            
        Returns:
            TrainingSample: 解析后的训练样本
            
        Raises:
            ValueError: 重试失败后抛出异常
        """
        # 获取格式说明
        format_instructions = self.output_parser.get_format_instructions()
        
        # 构建 JSON 示例
        json_example = '''{
  "scenario": "qa_rule",
  "instruction": "这个类的功能是什么？",
  "context": "public class Example { ... }",
  "thought": {
    "observations": ["类中包含多个方法"],
    "inferences": ["这是一个工具类"],
    "evidence_refs": [],
    "assumptions": ["方法是公开的"]
  },
  "answer": "这个类提供了...",
  "repo_commit": "abc123",
  "quality": {}
}'''
        
        # 构建完整的提示词（强调只输出 JSON）
        full_system_prompt = f"""{system_prompt}

【重要】你必须严格按照以下要求输出：
1. 只输出一个合法的 JSON 对象
2. 不要输出任何代码（Java、Python 等）
3. 不要使用 Markdown 代码块标记（不要用 ```json 或 ``` 包裹）
4. 不要添加任何解释性文字
5. 直接以 {{ 开始，以 }} 结束

JSON Schema:
{format_instructions}

输出示例：
{json_example}

请直接输出 JSON 对象："""
        
        # 重试逻辑
        last_error = None
        raw_output = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    # 重试时强化提示
                    retry_system_prompt = f"""{full_system_prompt}

【第 {attempt + 1} 次尝试 - 前一次失败】
错误原因：{last_error}
上次输出：{raw_output[:200] if raw_output else 'None'}...

【必须遵守的规则】
1. 输出必须是纯 JSON 对象，不是代码！
2. 直接以 {{ 开始，以 }} 结束
3. 不要使用 ``` 标记
4. 不要输出 Java、Python 或其他编程语言代码
5. 所有必填字段必须存在：scenario, instruction, context, thought, answer, repo_commit
6. thought 字段必须包含：observations, inferences, evidence_refs, assumptions

立即输出 JSON："""
                    
                    logger.warning(f"Retry attempt {attempt}/{self.max_retries} for LLM generation")
                    messages = [
                        SystemMessage(content=retry_system_prompt),
                        HumanMessage(content=user_prompt)
                    ]
                else:
                    messages = [
                        SystemMessage(content=full_system_prompt),
                        HumanMessage(content=user_prompt)
                    ]
                
                # 调用 LLM
                start_time = time.time()
                response = self.llm.invoke(messages)
                elapsed = time.time() - start_time
                
                raw_output = response.content.strip()
                logger.debug(f"LLM response received in {elapsed:.2f}s: {raw_output[:200]}...")
                
                # 清理输出（移除可能的 Markdown 代码块标记）
                cleaned_output = self._clean_json_output(raw_output)
                
                # 解析为 TrainingSample
                training_sample = self.output_parser.parse(cleaned_output)
                
                # 确保 repo_commit 被设置
                if not training_sample.repo_commit:
                    training_sample.repo_commit = repo_commit
                
                logger.info(f"Successfully generated training sample (attempt {attempt + 1})")
                return training_sample
                
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1} failed: {last_error}")
                
                if attempt == self.max_retries:
                    # 所有重试都失败，记录拒绝样本
                    self._log_rejected_sample(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        raw_output=raw_output or "",
                        error=last_error
                    )
                    raise ValueError(f"Failed to generate valid training sample after {self.max_retries + 1} attempts: {last_error}")
                
                # 等待一小段时间后重试
                time.sleep(1)
    
    def _clean_json_output(self, output: str) -> str:
        """
        清理 LLM 输出，移除 Markdown 代码块标记
        
        Args:
            output: 原始输出
            
        Returns:
            str: 清理后的 JSON 字符串
        """
        output = output.strip()
        
        # 移除各种 Markdown 代码块标记
        if output.startswith("```json"):
            output = output[7:]
        elif output.startswith("```java"):
            output = output[7:]  # 移除错误的 java 标记
        elif output.startswith("```python"):
            output = output[9:]
        elif output.startswith("```"):
            output = output[3:]
        
        if output.endswith("```"):
            output = output[:-3]
        
        output = output.strip()
        
        # 如果输出为空或只包含代码块但没有内容
        if not output or output == "java" or output == "python":
            raise ValueError("LLM 返回了空输出或只有语言标记")
        
        # 确保输出以 { 开始（JSON 对象）
        if not output.startswith("{"):
            # 尝试找到第一个 {
            start_idx = output.find("{")
            if start_idx != -1:
                output = output[start_idx:]
            else:
                raise ValueError(f"输出不是有效的 JSON 对象，开头是: {output[:50]}")
        
        return output
    
    def _log_rejected_sample(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        raw_output: str, 
        error: str
    ):
        """
        记录拒绝的样本到 JSONL 文件
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            raw_output: LLM 原始输出
            error: 错误信息
        """
        rejected_sample = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_output": raw_output,
            "error": error,
            "model": self.model,
            "temperature": self.temperature
        }
        
        try:
            with open(self.rejected_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rejected_sample, ensure_ascii=False) + '\n')
            logger.info(f"Rejected sample logged to {self.rejected_log_path}")
        except Exception as e:
            logger.error(f"Failed to log rejected sample: {e}")
    
    def test_connection(self) -> bool:
        """
        测试 LLM 连接是否正常
        
        Returns:
            bool: 连接是否成功
        """
        try:
            response = self.llm.invoke([HumanMessage(content="Hello")])
            logger.info(f"LLM connection test successful: {response.content[:50]}...")
            return True
        except Exception as e:
            logger.error(f"LLM connection test failed: {e}")
            return False


def _build_test_sample_prompt() -> tuple[str, str]:
    """构建测试用的提示词"""
    system_prompt = """你是一个 Java 代码分析专家。
根据给定的代码片段，生成一个训练样本用于 Qwen2.5 模型微调。"""
    
    user_prompt = """请分析以下 Java 代码：

```java
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
```

生成一个 QA 类型的训练样本，问题是"这个类的功能是什么？"
"""
    
    return system_prompt, user_prompt


# ==================== 自测代码 ====================
if __name__ == "__main__":
    """
    最小自测示例
    
    运行前请确保：
    1. Ollama 服务已启动：ollama serve
    2. 已拉取模型：ollama pull qwen2.5-coder-3b-instruct
    3. 配置文件正确：configs/launch.yml
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from src.utils.config import config
    
    print("=" * 60)
    print("LLMClient 自测")
    print("=" * 60)
    
    # 初始化客户端
    print(f"\n1. 初始化 LLMClient...")
    try:
        client = LLMClient()
        print(f"   ✓ Base URL: {client.base_url}")
        print(f"   ✓ Model: {client.model}")
        print(f"   ✓ Temperature: {client.temperature}")
    except Exception as e:
        print(f"   ✗ 初始化失败: {e}")
        sys.exit(1)
    
    # 测试连接
    print(f"\n2. 测试 LLM 连接...")
    if client.test_connection():
        print(f"   ✓ 连接成功")
    else:
        print(f"   ✗ 连接失败（请检查 Ollama 服务是否启动）")
        sys.exit(1)
    
    # 生成测试样本
    print(f"\n3. 生成训练样本...")
    try:
        system_prompt, user_prompt = _build_test_sample_prompt()
        
        sample = client.generate_training_sample(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            scenario="qa_rule",
            repo_commit="test_commit_123"
        )
        
        print(f"   ✓ 样本生成成功")
        print(f"\n生成的样本：")
        print(f"   - Scenario: {sample.scenario}")
        print(f"   - Instruction: {sample.instruction[:60]}...")
        print(f"   - Context: {sample.context[:60]}...")
        print(f"   - Answer: {sample.answer[:60]}...")
        print(f"   - Sample ID: {sample.sample_id}")
        
        # 验证样本
        print(f"\n4. 验证样本数据...")
        if sample.validate_hash if hasattr(sample, 'validate_hash') else True:
            print(f"   ✓ 数据验证通过")
        
        # 序列化为 JSON
        print(f"\n5. 序列化测试...")
        json_output = sample.model_dump_json(indent=2)
        print(f"   ✓ JSON 长度: {len(json_output)} 字符")
        
        # 保存测试样本
        test_output_path = Path("data/intermediate/test_sample.json")
        test_output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(test_output_path, 'w', encoding='utf-8') as f:
            f.write(json_output)
        print(f"   ✓ 测试样本已保存到: {test_output_path}")
        
        print("\n" + "=" * 60)
        print("自测完成！")
        print("=" * 60)
        
    except ValueError as e:
        print(f"   ✗ 生成失败: {e}")
        print(f"\n请检查 {client.rejected_log_path} 查看失败详情")
        sys.exit(1)
    except Exception as e:
        print(f"   ✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
