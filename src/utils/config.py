"""
配置管理 - 读取 YAML 配置文件并支持环境变量覆盖
"""
import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    """配置管理类 - 单例模式"""
    
    _instance = None
    _config: dict = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化配置（仅在第一次创建时执行）"""
        if not self._config:
            self.reload()
    
    def reload(self, config_path: str | Path | None = None):
        """
        重新加载配置文件
        
        Args:
            config_path: 配置文件路径，默认为 configs/pipeline.yaml
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "configs" / "pipeline.yaml"
        else:
            config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        # 读取 YAML 配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f) or {}
        
        # 应用环境变量覆盖
        self._apply_env_overrides()
    
    def _apply_env_overrides(self):
        """应用环境变量覆盖配置"""
        # LLM 配置覆盖
        if 'OLLAMA_BASE_URL' in os.environ:
            base_url = os.environ['OLLAMA_BASE_URL']
            # 自动添加 /v1 后缀（如果没有）
            if not base_url.endswith('/v1'):
                base_url = base_url.rstrip('/') + '/v1'
            self._set_nested('llm.base_url', base_url)
        
        if 'OLLAMA_MODEL' in os.environ:
            self._set_nested('llm.model', os.environ['OLLAMA_MODEL'])
        
        if 'LLM_TEMPERATURE' in os.environ:
            self._set_nested('llm.temperature', float(os.environ['LLM_TEMPERATURE']))
        
        if 'LLM_MAX_TOKENS' in os.environ:
            self._set_nested('llm.max_tokens', int(os.environ['LLM_MAX_TOKENS']))
        
        if 'LLM_TIMEOUT' in os.environ:
            self._set_nested('llm.timeout', int(os.environ['LLM_TIMEOUT']))
        
        # 仓库配置覆盖
        if 'REPO_PATH' in os.environ:
            self._set_nested('repo.path', os.environ['REPO_PATH'])
        
        if 'REPO_COMMIT' in os.environ:
            self._set_nested('repo.commit', os.environ['REPO_COMMIT'])
        
        # 日志级别覆盖
        if 'LOG_LEVEL' in os.environ:
            self._set_nested('logging.level', os.environ['LOG_LEVEL'])
    
    def _set_nested(self, key_path: str, value: Any):
        """
        设置嵌套字典的值
        
        Args:
            key_path: 点分隔的键路径，如 "llm.base_url"
            value: 要设置的值
        """
        keys = key_path.split('.')
        d = self._config
        
        for key in keys[:-1]:
            if key not in d or not isinstance(d[key], dict):
                d[key] = {}
            d = d[key]
        
        d[keys[-1]] = value
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key_path: 点分隔的键路径，如 "llm.base_url"
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_section(self, section: str) -> dict:
        """
        获取配置的某个部分
        
        Args:
            section: 配置节名称，如 "llm"
            
        Returns:
            配置节字典
        """
        return self._config.get(section, {})
    
    def get_config(self) -> dict:
        """
        获取完整配置字典
        
        Returns:
            完整配置字典
        """
        return self._config
    
    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.get(key)
    
    def __contains__(self, key: str) -> bool:
        """支持 in 运算符"""
        return self.get(key) is not None
    
    @property
    def repo_path(self) -> str:
        """仓库路径"""
        return self.get('repo.path', '')
    
    @property
    def repo_commit(self) -> str:
        """仓库 commit hash"""
        return self.get('repo.commit', '')
    
    @property
    def ollama_base_url(self) -> str:
        """Ollama 服务地址"""
        return self.get('llm.base_url', 'http://localhost:11434/v1')
    
    @property
    def ollama_model(self) -> str:
        """Ollama 模型名称"""
        return self.get('llm.model', 'qwen2.5-coder-3b-instruct')
    
    @property
    def max_chars_per_symbol(self) -> int:
        """单个符号最大字符数"""
        return self.get('parser.max_chars_per_symbol', 5000)
    
    @property
    def batch_size(self) -> int:
        """批次大小"""
        return self.get('generation.batch_size', 10)
    
    @property
    def top_k_context(self) -> int:
        """上下文数量"""
        return self.get('generation.top_k_context', 5)
    
    @property
    def ignore_paths(self) -> list[str]:
        """忽略的路径模式"""
        return self.get('parser.ignore_paths', [])
    
    @property
    def output_dirs(self) -> dict[str, str]:
        """输出目录映射"""
        return self.get_section('output')
    
    def ensure_output_dirs(self):
        """确保所有输出目录存在"""
        for dir_path in self.output_dirs.values():
            Path(dir_path).mkdir(parents=True, exist_ok=True)


# 全局配置实例
config = Config()


def get_config() -> Config:
    """获取全局配置实例"""
    return config


def reload_config(config_path: str | Path | None = None):
    """重新加载配置"""
    config.reload(config_path)
