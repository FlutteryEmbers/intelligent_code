"""
Java 解析器 - 使用 tree-sitter 解析 Java 代码
"""
import json
import time
from pathlib import Path
from typing import Generator

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, Node

from src.parser.base import BaseParser
from src.utils.schemas import CodeSymbol, Annotation, ParsingReport, sha256_text
from src.utils.logger import get_logger

logger = get_logger(__name__)


class JavaParser(BaseParser):
    """
    Java 代码解析器
    
    使用 tree-sitter-java 解析 Java 源码，提取：
    - 类（class/interface/enum）
    - 方法（method）
    - 字段（field）
    - 注解（特别是 Spring 注解）
    - JavaDoc 注释
    """
    
    # Spring 常见注解列表
    SPRING_ANNOTATIONS = {
        'RestController', 'Controller', 'Service', 'Repository', 'Component',
        'Configuration', 'Bean', 'Autowired', 'Value', 'Qualifier',
        'GetMapping', 'PostMapping', 'PutMapping', 'DeleteMapping', 'RequestMapping',
        'PathVariable', 'RequestParam', 'RequestBody', 'ResponseBody',
        'Transactional', 'Async', 'Scheduled', 'EnableAsync',
        'SpringBootApplication', 'ComponentScan', 'EnableAutoConfiguration'
    }
    
    def __init__(self, config: dict | None = None):
        """初始化 Java 解析器"""
        super().__init__(config)
        
        # 初始化 tree-sitter
        # Language 需要两个参数：language() 返回值和语言名称
        self.java_language = Language(tsjava.language(), "java")
        self.parser = Parser()
        self.parser.set_language(self.java_language)
        
        # 字符预算（从配置读取）
        self.max_chars_per_symbol = self.config.get('max_chars_per_symbol', 12000)
        
        # 解析跳过记录路径
        self.skip_log_path = Path('data/raw/extracted/parse_skipped.jsonl')
        self.skip_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"JavaParser initialized with max_chars_per_symbol={self.max_chars_per_symbol}")
    
    def parse_repo(self, repo_path: str, repo_commit: str) -> list[CodeSymbol]:
        """
        解析整个 Java 代码仓库
        
        Args:
            repo_path: 仓库根目录路径
            repo_commit: 当前 commit hash
            
        Returns:
            list[CodeSymbol]: 解析出的所有代码符号列表
        """
        start_time = time.time()
        repo_path_obj = Path(repo_path)
        
        if not repo_path_obj.exists():
            raise FileNotFoundError(f"Repository path not found: {repo_path}")
        
        logger.info(f"Starting to parse Java repository: {repo_path}")
        
        symbols = []
        errors = []
        parsed_files = 0
        failed_files = 0
        
        # 遍历所有 Java 文件
        for java_file in self.iter_source_files(repo_path_obj):
            try:
                # 解析单个文件
                file_symbols = self.parse_file(java_file, repo_commit, repo_path_obj)
                symbols.extend(file_symbols)
                parsed_files += 1
                
                if parsed_files % 10 == 0:
                    logger.info(f"Parsed {parsed_files} files, {len(symbols)} symbols so far")
                    
            except Exception as e:
                failed_files += 1
                error_info = {
                    'file': str(java_file),
                    'error': str(e),
                    'type': type(e).__name__
                }
                errors.append(error_info)
                logger.error(f"Failed to parse {java_file}: {e}")
        
        # 生成报告
        parsing_time = time.time() - start_time
        report = self.generate_report(
            repo_path=repo_path,
            repo_commit=repo_commit,
            symbols=symbols,
            parsing_time=parsing_time,
            errors=errors
        )
        
        logger.info(f"Parsing completed: {parsed_files} files, {len(symbols)} symbols, {failed_files} errors")
        
        # 保存结果
        self._save_symbols(symbols, report)
        
        return symbols
    
    def parse_file(self, file_path: Path, repo_commit: str, repo_root: Path | None = None) -> list[CodeSymbol]:
        """
        解析单个 Java 文件
        
        Args:
            file_path: Java 文件路径
            repo_commit: 仓库 commit hash
            repo_root: 仓库根目录（用于计算相对路径）
            
        Returns:
            list[CodeSymbol]: 该文件中解析出的符号列表
        """
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            with open(file_path, 'r', encoding='latin-1') as f:
                source_code = f.read()
        
        # 解析语法树
        tree = self.parser.parse(bytes(source_code, 'utf-8'))
        root_node = tree.root_node
        
        # 计算相对路径
        if repo_root:
            try:
                relative_path = file_path.relative_to(repo_root).as_posix()
            except ValueError:
                relative_path = file_path.name
        else:
            relative_path = file_path.name
        
        # 提取 package 名称
        package_name = self._extract_package(root_node, source_code)
        
        symbols = []
        
        # 遍历所有类声明
        for class_node in self._find_nodes_by_type(root_node, ['class_declaration', 'interface_declaration', 'enum_declaration']):
            class_symbols = self._parse_class(
                class_node=class_node,
                source_code=source_code,
                file_path=relative_path,
                package_name=package_name,
                repo_commit=repo_commit
            )
            symbols.extend(class_symbols)
        
        return symbols
    
    def _parse_class(
        self,
        class_node: Node,
        source_code: str,
        file_path: str,
        package_name: str,
        repo_commit: str
    ) -> list[CodeSymbol]:
        """解析类及其成员"""
        symbols = []
        
        # 获取类名
        class_name = self._get_class_name(class_node, source_code)
        if not class_name:
            return symbols
        
        # 构建完全限定名
        if package_name:
            qualified_class_name = f"{package_name}.{class_name}"
        else:
            qualified_class_name = class_name
        
        # 解析类上的注解
        class_annotations = self._extract_annotations(class_node, source_code)
        
        # 解析类的 JavaDoc
        class_doc = self._extract_javadoc(class_node, source_code)
        
        # 遍历类的方法
        for method_node in self._find_methods_in_class(class_node):
            try:
                method_symbol = self._parse_method(
                    method_node=method_node,
                    source_code=source_code,
                    file_path=file_path,
                    class_qualified_name=qualified_class_name,
                    repo_commit=repo_commit
                )
                if method_symbol:
                    symbols.append(method_symbol)
            except Exception as e:
                logger.warning(f"Failed to parse method in {qualified_class_name}: {e}")
                self._log_skipped(file_path, qualified_class_name, str(e))
        
        return symbols
    
    def _parse_method(
        self,
        method_node: Node,
        source_code: str,
        file_path: str,
        class_qualified_name: str,
        repo_commit: str
    ) -> CodeSymbol | None:
        """解析单个方法"""
        # 获取方法名
        method_name = self._get_method_name(method_node, source_code)
        if not method_name:
            return None
        
        # 构建完全限定名
        qualified_name = f"{class_qualified_name}.{method_name}"
        
        # 提取方法源码
        start_byte = method_node.start_byte
        end_byte = method_node.end_byte
        method_source = source_code[start_byte:end_byte]
        
        # 计算行号（tree-sitter 是 0-based，我们需要 1-based）
        start_line = method_node.start_point[0] + 1
        end_line = method_node.end_point[0] + 1
        
        # 解析注解
        annotations = self._extract_annotations(method_node, source_code)
        
        # 解析 JavaDoc
        doc = self._extract_javadoc(method_node, source_code)
        
        # 处理源码长度限制
        original_chars = len(method_source)
        truncated = False
        
        if original_chars > self.max_chars_per_symbol:
            method_source = self._truncate_source(method_source, original_chars)
            truncated = True
        
        # 生成 symbol_id
        symbol_id = CodeSymbol.make_symbol_id(file_path, qualified_name, start_line)
        
        # 计算 source_hash
        source_hash = sha256_text(method_source)
        
        # 构建元数据
        metadata = {
            'class_name': class_qualified_name.split('.')[-1],
            'method_name': method_name,
            'has_annotations': len(annotations) > 0,
            'has_javadoc': doc is not None
        }
        
        if truncated:
            metadata['truncated'] = True
            metadata['original_chars'] = original_chars
        
        # 创建 CodeSymbol
        symbol = CodeSymbol(
            symbol_id=symbol_id,
            symbol_type='method',
            name=method_name,
            qualified_name=qualified_name,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            source=method_source,
            doc=doc,
            annotations=annotations,
            metadata=metadata,
            repo_commit=repo_commit,
            source_hash=source_hash
        )
        
        return symbol
    
    def _truncate_source(self, source: str, original_chars: int) -> str:
        """
        截断过长的源码
        
        策略：保留头部和尾部，中间用标记替代
        """
        max_chars = self.max_chars_per_symbol
        
        # 计算头尾各保留多少字符
        head_chars = max_chars // 2 - 50  # 减去标记长度
        tail_chars = max_chars // 2 - 50
        
        head = source[:head_chars]
        tail = source[-tail_chars:]
        
        truncated = f"{head}\n\n... /* TRUNCATED: {original_chars - max_chars} chars omitted */ ...\n\n{tail}"
        
        return truncated
    
    def _extract_package(self, root_node: Node, source_code: str) -> str:
        """提取 package 名称"""
        for node in self._find_nodes_by_type(root_node, ['package_declaration']):
            # package_declaration 包含一个 scoped_identifier 或 identifier
            for child in node.children:
                if child.type in ['scoped_identifier', 'identifier']:
                    return source_code[child.start_byte:child.end_byte]
        return ""
    
    def _get_class_name(self, class_node: Node, source_code: str) -> str | None:
        """获取类名"""
        for child in class_node.children:
            if child.type == 'identifier':
                return source_code[child.start_byte:child.end_byte]
        return None
    
    def _get_method_name(self, method_node: Node, source_code: str) -> str | None:
        """获取方法名"""
        for child in method_node.children:
            if child.type == 'identifier':
                return source_code[child.start_byte:child.end_byte]
        return None
    
    def _extract_annotations(self, node: Node, source_code: str) -> list[Annotation]:
        """
        提取节点上的注解
        
        支持解析常见的注解格式：
        - @AnnotationName
        - @AnnotationName(value)
        - @AnnotationName(key=value, key2=value2)
        """
        annotations = []
        
        # 查找 modifiers 节点，它包含注解
        for child in node.children:
            if child.type == 'modifiers':
                for modifier_child in child.children:
                    if modifier_child.type == 'marker_annotation' or \
                       modifier_child.type == 'annotation':
                        ann = self._parse_annotation_node(modifier_child, source_code)
                        if ann:
                            annotations.append(ann)
        
        return annotations
    
    def _parse_annotation_node(self, ann_node: Node, source_code: str) -> Annotation | None:
        """解析单个注解节点"""
        raw_text = source_code[ann_node.start_byte:ann_node.end_byte]
        
        # 获取注解名称
        name = None
        arguments = {}
        
        for child in ann_node.children:
            if child.type == 'identifier' or child.type == 'scoped_identifier':
                name = source_code[child.start_byte:child.end_byte]
            elif child.type == 'annotation_argument_list':
                # 解析参数列表
                arguments = self._parse_annotation_arguments(child, source_code)
        
        if not name:
            return None
        
        # 移除 @ 前缀
        if name.startswith('@'):
            name = name[1:]
        
        return Annotation(
            name=name,
            arguments=arguments if arguments else None,
            raw_text=raw_text
        )
    
    def _parse_annotation_arguments(self, arg_list_node: Node, source_code: str) -> dict:
        """解析注解参数"""
        arguments = {}
        
        for child in arg_list_node.children:
            if child.type == 'element_value_pair':
                # key = value 格式
                key = None
                value = None
                for pair_child in child.children:
                    if pair_child.type == 'identifier':
                        key = source_code[pair_child.start_byte:pair_child.end_byte]
                    elif pair_child.type in ['string_literal', 'identifier', 'integer_literal', 'boolean_literal']:
                        value = source_code[pair_child.start_byte:pair_child.end_byte]
                
                if key and value:
                    arguments[key] = value
            elif child.type in ['string_literal', 'identifier']:
                # 单个值（默认是 value 参数）
                arguments['value'] = source_code[child.start_byte:child.end_byte]
        
        return arguments
    
    def _extract_javadoc(self, node: Node, source_code: str) -> str | None:
        """提取 JavaDoc 注释"""
        # JavaDoc 通常在节点之前
        # 我们需要查找前面的注释节点
        
        # 简单实现：查找节点开始位置之前的文本，寻找 /** ... */
        start_line = node.start_point[0]
        
        # 向上查找注释
        lines = source_code.split('\n')
        
        # 从当前行向上查找
        javadoc_lines = []
        for i in range(start_line - 1, max(0, start_line - 20), -1):
            line = lines[i].strip()
            
            if line.endswith('*/'):
                javadoc_lines.insert(0, line)
                # 继续向上查找
                for j in range(i - 1, -1, -1):
                    prev_line = lines[j].strip()
                    javadoc_lines.insert(0, prev_line)
                    if prev_line.startswith('/**'):
                        # 找到了 JavaDoc 开始
                        javadoc_text = '\n'.join(javadoc_lines)
                        return javadoc_text
                break
            elif line.startswith('*') or line.startswith('/**'):
                javadoc_lines.insert(0, line)
            elif line and not line.startswith('//'):
                # 遇到非注释行，停止查找
                break
        
        return None
    
    def _find_nodes_by_type(self, node: Node, types: list[str]) -> Generator[Node, None, None]:
        """递归查找指定类型的节点"""
        if node.type in types:
            yield node
        
        for child in node.children:
            yield from self._find_nodes_by_type(child, types)
    
    def _find_methods_in_class(self, class_node: Node) -> Generator[Node, None, None]:
        """查找类中的所有方法"""
        for child in class_node.children:
            if child.type == 'class_body':
                for body_child in child.children:
                    if body_child.type == 'method_declaration':
                        yield body_child
                    elif body_child.type == 'constructor_declaration':
                        yield body_child
    
    def iter_source_files(self, repo_path: Path) -> Generator[Path, None, None]:
        """迭代仓库中的所有 Java 文件"""
        for java_file in repo_path.rglob('*.java'):
            # 检查是否应该忽略
            if self.should_ignore(java_file):
                logger.debug(f"Ignoring file: {java_file}")
                continue
            
            yield java_file
    
    def _save_symbols(self, symbols: list[CodeSymbol], report: ParsingReport):
        """保存解析结果"""
        # 保存 symbols 到 JSONL
        symbols_path = Path('data/raw/extracted/symbols.jsonl')
        symbols_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(symbols_path, 'w', encoding='utf-8') as f:
            for symbol in symbols:
                f.write(symbol.model_dump_json() + '\n')
        
        logger.info(f"Saved {len(symbols)} symbols to {symbols_path}")
        
        # 保存元数据
        meta_path = Path('data/raw/repo_meta/repo_meta.json')
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(report.model_dump_json(indent=2))
        
        logger.info(f"Saved repository metadata to {meta_path}")
        
        # 保存详细报告
        report_path = Path('data/reports/parsing_report.json')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report.model_dump_json(indent=2))
        
        logger.info(f"Saved detailed report to {report_path}")
    
    def _log_skipped(self, file_path: str, location: str, reason: str):
        """记录跳过的解析项"""
        skip_entry = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'file_path': file_path,
            'location': location,
            'reason': reason
        }
        
        try:
            with open(self.skip_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(skip_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Failed to log skipped entry: {e}")


def get_repo_commit(repo_path: str) -> str:
    """
    获取仓库的 commit hash
    
    尝试从 git 获取，如果失败则返回时间戳
    """
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    # 如果无法获取 git commit，使用时间戳
    return f"snapshot_{int(time.time())}"
