import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.io.file_ops import load_prompt_template, clean_llm_json_output
from .llm_client import LLMClient

logger = get_logger(__name__)

class BaseGenerator:
    """
    发电机基类 - 统一 Prompt 管理与 LLM 交互逻辑
    
    统一了以下核心工作流：
    1. 动态加载骨架模板 (system.txt / user.txt)
    2. 结合语言 Profile 注入角色定义 (role_identity) 与 共通规则 (json_rules)
    3. 封装带有重试和错误处理的 LLM 调用
    """
    
    def __init__(self, scenario: str, config: Optional[Config] = None):
        """
        初始化发电机
        
        Args:
            scenario: 场景名称 (如 'qa_rule', 'arch_design', 'method_profile')
            config: 全局配置对象
        """
        self.scenario = scenario
        self.config = config or Config()
        self.llm_client = LLMClient(config=self.config)
        
        # 预加载核心骨架 (System Message)
        self.system_skeleton = self._load_template("system")
        
    def _load_template(self, template_name: str, scenario: Optional[str] = None) -> str:
        """
        从 configs/prompts/{scenario}/{template_name}.txt 加载模板
        
        Args:
            template_name: 模板文件名 (不含扩展名)
            scenario: 覆盖当前场景，用于加载 common 模板
            
        Returns:
            str: 模板内容
        """
        target_scenario = scenario or self.scenario
        if target_scenario == "common":
            base_dir = Path("configs/prompts/common")
        else:
            base_dir = Path("configs/prompts") / target_scenario
            
        # 优先查找 .txt，次选 .yaml
        for ext in [".txt", ".yaml"]:
            path = base_dir / f"{template_name}{ext}"
            if path.exists():
                return load_prompt_template(str(path))
        
        logger.warning(f"Template '{template_name}' not found in {base_dir}")
        return ""

    def _get_common_json_rules(self) -> str:
        """获取通用的 JSON 格式规则"""
        return self._load_template("json_rules", scenario="common")

    def _get_language_profile(self):
        """获取当前语言的 Profile"""
        return self.config.get_language_profile()

    def _build_composed_system_prompt(self, **kwargs) -> str:
        """
        组装系统提示词
        
        注入变量：
        - role_identity: 来自 language/*.yaml
        - language: 当前项目语言
        - common_json_rules: 来自 prompts/common/json_rules.txt
        """
        lang_profile = self._get_language_profile()
        language_name = self.config.get("language.name", "java").capitalize()
        
        # 角色定义映射: e.g. qa_rule_role
        role_key = f"{self.scenario}_role"
        role_identity = lang_profile.get("system_prompts", {}).get(role_key, "")
        
        common_json_rules = self._get_common_json_rules()
        
        try:
            return self.system_skeleton.format(
                role_identity=role_identity,
                language=language_name,
                common_json_rules=common_json_rules,
                **kwargs
            )
        except KeyError as e:
            logger.error(f"Missing required placeholder {e} in system skeleton for {self.scenario}")
            # Fallback: return unformatted or partial
            return self.system_skeleton

    def _build_composed_user_prompt(self, template_name: str, **kwargs) -> str:
        """
        组装用户提示词
        
        Args:
            template_name: 用户提示词模板名称
            **kwargs: 业务相关的变量 (如 source_code, profile 等)
        """
        template = self._load_template(template_name)
        if not template:
            raise ValueError(f"User template '{template_name}' missing for {self.scenario}")
            
        lang_profile = self._get_language_profile()
        language_name = self.config.get("language.name", "java").capitalize()
        role_key = f"{self.scenario}_role"
        role_identity = lang_profile.get("system_prompts", {}).get(role_key, "")
        common_json_rules = self._get_common_json_rules()
        
        try:
            return template.format(
                role_identity=role_identity,
                language=language_name,
                common_json_rules=common_json_rules,
                **kwargs
            )
        except KeyError as e:
            logger.error(f"Missing business placeholder {e} in template '{template_name}'")
            raise

    def generate_with_retry(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        执行带有重试机制的 LLM 生成
        
        Returns:
            Dict: 解析后的 JSON 对象
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = self.llm_client.llm.invoke(
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt)
                    ],
                    max_tokens=self.llm_client.max_tokens
                )
                raw_output = response.content.strip()
                cleaned = clean_llm_json_output(raw_output)
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.error(f"[{self.scenario}] JSON Parsing Failed: {e}")
                logger.error(f"[{self.scenario}] Raw Output Snippet: {raw_output[:1000]}")  # Log first 1000 chars
                last_error = e
            except Exception as e:
                last_error = e
                logger.warning(f"[{self.scenario}] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    time.sleep(1)
        
        logger.error(f"[{self.scenario}] All {max_retries + 1} generation attempts failed.")
        raise last_error
