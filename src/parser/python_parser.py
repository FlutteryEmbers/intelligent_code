"""Python Parser - Extract symbols from Python code (placeholder for tree-sitter implementation)"""
from pathlib import Path
from typing import List
import ast
import re

from src.utils.core.schemas import CodeSymbol, Annotation
from src.utils.core.logger import get_logger
from src.parser.base import BaseParser

logger = get_logger(__name__)


class PythonParser(BaseParser):
    """
    Python code parser using AST
    
    TODO: Replace with tree-sitter-python for better accuracy
    Currently uses Python's built-in ast module as placeholder
    """
    
    def __init__(self, config=None):
        """Initialize parser"""
        super().__init__(config)
        # BaseParser already loaded profile and set these attributes:
        # self.max_chars_per_symbol, self.include_private, self.include_test, self.file_extensions
        logger.info(f"PythonParser initialized with max_chars_per_symbol={self.max_chars_per_symbol}")
        logger.info(f"File extensions: {self.file_extensions}")
        logger.info(f"Ignore paths: {len(self.ignore_paths)} patterns")
    
    def parse_file(self, file_path: Path, repo_commit: str = "unknown", repo_root: Path = None) -> List[CodeSymbol]:
        """Parse a single Python file"""
        # Use repo_root for calculating relative paths, fallback to file_path.parent
        if repo_root is None:
            repo_root = Path.cwd()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(file_path))
            symbols = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    symbol = self._extract_function(node, file_path, content, repo_commit, repo_root)
                    if symbol:
                        symbols.append(symbol)
                elif isinstance(node, ast.ClassDef):
                    symbol = self._extract_class(node, file_path, content, repo_commit, repo_root)
                    if symbol:
                        symbols.append(symbol)
            
            return symbols
            
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []
    
    def _extract_function(self, node: ast.FunctionDef, file_path: Path, content: str, repo_commit: str, repo_root: Path) -> CodeSymbol | None:
        """Extract function symbol"""
        # Skip private functions if configured
        if not self.include_private and node.name.startswith('_') and not node.name.startswith('__'):
            return None
        
        # Skip test functions if configured
        if not self.include_test and (node.name.startswith('test_') or 'test' in str(file_path).lower()):
            return None
        
        # Extract decorators
        annotations = []
        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)
            if decorator_name:
                annotations.append(Annotation(
                    name=decorator_name,
                    arguments=None,
                    raw_text=f"@{decorator_name}"
                ))
        
        # Extract docstring
        doc = ast.get_docstring(node)
        
        # Get source code
        try:
            start_line = node.lineno
            end_line = node.end_lineno or start_line
            lines = content.split('\n')
            source = '\n'.join(lines[start_line-1:end_line])
            if len(source) > self.max_chars_per_symbol:
                source = source[:self.max_chars_per_symbol] + "\n... (truncated)"
        except:
            source = f"def {node.name}(...): pass"
        
        # Build qualified name (simple version)
        qualified_name = f"{file_path.stem}.{node.name}"
        
        # Calculate relative path with fallback
        try:
            relative_path = file_path.relative_to(repo_root)
        except ValueError:
            # If file_path is not relative to repo_root, use file name
            relative_path = file_path.name
        
        symbol_id = CodeSymbol.make_symbol_id(
            str(relative_path),
            qualified_name,
            node.lineno
        )
        
        from src.utils.core.schemas import sha256_text
        
        return CodeSymbol(
            symbol_id=symbol_id,
            symbol_type="method",
            name=node.name,
            qualified_name=qualified_name,
            file_path=str(relative_path),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            source=source,
            doc=doc,
            annotations=annotations,
            metadata={"language": "python"},
            repo_commit=repo_commit,
            source_hash=sha256_text(source)
        )
    
    def _extract_class(self, node: ast.ClassDef, file_path: Path, content: str, repo_commit: str, repo_root: Path) -> CodeSymbol | None:
        """Extract class symbol"""
        # Skip private classes if configured
        if not self.include_private and node.name.startswith('_'):
            return None
        
        # Extract decorators
        annotations = []
        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)
            if decorator_name:
                annotations.append(Annotation(
                    name=decorator_name,
                    arguments=None,
                    raw_text=f"@{decorator_name}"
                ))
        
        # Extract docstring
        doc = ast.get_docstring(node)
        
        # Get source code
        try:
            start_line = node.lineno
            end_line = node.end_lineno or start_line
            lines = content.split('\n')
            source = '\n'.join(lines[start_line-1:end_line])
            if len(source) > self.max_chars_per_symbol:
                source = source[:self.max_chars_per_symbol] + "\n... (truncated)"
        except:
            source = f"class {node.name}: pass"
        
        qualified_name = f"{file_path.stem}.{node.name}"
        
        # Calculate relative path with fallback
        try:
            relative_path = file_path.relative_to(repo_root)
        except ValueError:
            # If file_path is not relative to repo_root, use file name
            relative_path = file_path.name
        
        symbol_id = CodeSymbol.make_symbol_id(
            str(relative_path),
            qualified_name,
            node.lineno
        )
        
        from src.utils.core.schemas import sha256_text
        
        return CodeSymbol(
            symbol_id=symbol_id,
            symbol_type="class",
            name=node.name,
            qualified_name=qualified_name,
            file_path=str(relative_path),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            source=source,
            doc=doc,
            annotations=annotations,
            metadata={"language": "python"},
            repo_commit=repo_commit,
            source_hash=sha256_text(source)
        )
    
    def _get_decorator_name(self, decorator) -> str | None:
        """Extract decorator name from AST node"""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        return None
    
    def parse_repo(self, repo_path: str, repo_commit: str) -> List[CodeSymbol]:
        """Parse entire Python repository"""
        import time
        start_time = time.time()
        repo_path_obj = Path(repo_path)
        
        if not repo_path_obj.exists():
            raise FileNotFoundError(f"Repository path not found: {repo_path}")
        
        logger.info(f"Starting to parse Python repository: {repo_path}")
        
        symbols = []
        errors = []
        parsed_files = 0
        failed_files = 0
        
        # Iterate all source files based on profile's file_extensions
        for py_file in self.iter_source_files(repo_path_obj):
            try:
                file_symbols = self.parse_file(py_file, repo_commit, repo_root=repo_path_obj)
                symbols.extend(file_symbols)
                parsed_files += 1
                
                if parsed_files % 10 == 0:
                    logger.info(f"Parsed {parsed_files} files, {len(symbols)} symbols so far")
                    
            except Exception as e:
                failed_files += 1
                error_info = {
                    'file': str(py_file),
                    'error': str(e),
                    'type': type(e).__name__
                }
                errors.append(error_info)
                logger.error(f"Failed to parse {py_file}: {e}")
        
        parsing_time = time.time() - start_time
        logger.info(f"Parsing completed: {parsed_files} files, {len(symbols)} symbols, {failed_files} errors")
        
        return symbols
    
    def iter_source_files(self, repo_path: Path):
        """Iterate source files in repository based on profile's file_extensions"""
        for ext in self.file_extensions:
            # Remove leading dot if present
            pattern = f"*{ext}" if ext.startswith('.') else f"*.{ext}"
            for source_file in repo_path.rglob(pattern):
                # Check if should ignore
                if self.should_ignore(source_file):
                    logger.debug(f"Ignoring file: {source_file}")
                    continue
                
                yield source_file
