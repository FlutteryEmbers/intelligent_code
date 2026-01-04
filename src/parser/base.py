"""
Parser 抽象基类 - 定义代码解析器的统一接口
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generator

from src.utils.schemas import CodeSymbol, ParsingReport


class BaseParser(ABC):
    """代码解析器抽象基类
    
    所有具体的语言解析器（如 JavaParser）都应继承此类并实现抽象方法
    """

    def __init__(self, config: dict | None = None):
        """
        初始化解析器
        
        Args:
            config: 解析器配置字典，可包含：
                - max_chars_per_symbol: 单个符号最大字符数
                - ignore_paths: 忽略的路径模式列表
                - include_private: 是否包含私有成员
                等
        """
        self.config = config or {}
        self.max_chars_per_symbol = self.config.get('max_chars_per_symbol', 5000)
        self.ignore_paths = self.config.get('ignore_paths', [])

    @abstractmethod
    def parse_repo(self, repo_path: str, repo_commit: str) -> list[CodeSymbol]:
        """
        解析整个代码仓库
        
        Args:
            repo_path: 仓库根目录路径
            repo_commit: 当前 commit hash（用于追溯）
            
        Returns:
            list[CodeSymbol]: 解析出的所有代码符号列表
            
        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("Subclass must implement parse_repo()")

    def parse_file(self, file_path: Path, repo_commit: str) -> list[CodeSymbol]:
        """
        解析单个文件（可选实现）
        
        Args:
            file_path: 文件路径
            repo_commit: 仓库 commit hash
            
        Returns:
            list[CodeSymbol]: 该文件中解析出的符号列表
        """
        raise NotImplementedError("Optional: implement parse_file() for incremental parsing")

    def should_ignore(self, path: Path) -> bool:
        """
        判断路径是否应该被忽略
        
        Args:
            path: 待检查的路径
            
        Returns:
            bool: True 表示应忽略
        """
        path_str = path.as_posix()
        for pattern in self.ignore_paths:
            if pattern in path_str:
                return True
        return False

    def truncate_source(self, source: str) -> str:
        """
        截断过长的源码
        
        Args:
            source: 原始源码
            
        Returns:
            str: 截断后的源码（如果超长则添加截断标记）
        """
        if len(source) <= self.max_chars_per_symbol:
            return source
        
        truncated = source[:self.max_chars_per_symbol]
        return f"{truncated}\n... [truncated, total {len(source)} chars]"

    def generate_report(
        self, 
        repo_path: str, 
        repo_commit: str,
        symbols: list[CodeSymbol],
        parsing_time: float,
        errors: list[dict] | None = None
    ) -> ParsingReport:
        """
        生成解析报告
        
        Args:
            repo_path: 仓库路径
            repo_commit: commit hash
            symbols: 解析出的符号列表
            parsing_time: 解析耗时（秒）
            errors: 错误列表
            
        Returns:
            ParsingReport: 解析报告对象
        """
        from collections import Counter
        
        symbols_by_type = Counter(s.symbol_type for s in symbols)
        files = {s.file_path for s in symbols}
        
        return ParsingReport(
            repo_path=str(repo_path),
            repo_commit=repo_commit,
            total_files=len(files),
            parsed_files=len(files),
            failed_files=0,
            total_symbols=len(symbols),
            symbols_by_type=dict(symbols_by_type),
            errors=errors or [],
            parsing_time_seconds=round(parsing_time, 2)
        )

    def iter_source_files(self, repo_path: Path) -> Generator[Path, None, None]:
        """
        迭代仓库中的源码文件（需子类根据语言实现）
        
        Args:
            repo_path: 仓库根目录
            
        Yields:
            Path: 源码文件路径
        """
        raise NotImplementedError("Subclass should implement iter_source_files()")
