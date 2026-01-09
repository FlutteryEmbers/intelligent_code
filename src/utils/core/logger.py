"""
日志工具 - 统一的日志配置和管理
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from .config import config


class LoggerManager:
    """日志管理器 - 单例模式"""
    
    _instance: Optional['LoggerManager'] = None
    _loggers: dict[str, logging.Logger] = {}
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化日志管理器"""
        if not self._initialized:
            self._setup_logging()
            self._initialized = True
    
    def _setup_logging(self):
        """设置日志配置"""
        # 确保日志目录存在
        log_file = config.get('logging.file', 'logs/pipeline.log')
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 获取日志级别和格式
        log_level = config.get('logging.level', 'INFO')
        log_format = config.get(
            'logging.format',
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 配置根日志器
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format=log_format,
            handlers=[
                # 文件处理器
                logging.FileHandler(log_file, encoding='utf-8'),
                # 控制台处理器
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取或创建指定名称的日志器
        
        Args:
            name: 日志器名称（通常使用 __name__）
            
        Returns:
            logging.Logger: 日志器实例
        """
        if name not in self._loggers:
            logger = logging.getLogger(name)
            self._loggers[name] = logger
        
        return self._loggers[name]


# 全局日志管理器实例
_logger_manager = LoggerManager()


def get_logger(name: str = __name__) -> logging.Logger:
    """
    获取日志器的便捷函数
    
    Args:
        name: 日志器名称，默认使用调用者的模块名
        
    Returns:
        logging.Logger: 日志器实例
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
        >>> logger.error("An error occurred", exc_info=True)
    """
    return _logger_manager.get_logger(name)
