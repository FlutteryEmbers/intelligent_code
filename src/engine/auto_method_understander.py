"""
Auto 模块 - 方法级理解生成器

为候选方法生成深度理解的 MethodProfile。
"""
import json
import time
from pathlib import Path
from typing import Generator

from src.utils.schemas import CodeSymbol, MethodProfile, EvidenceRef, sha256_text
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.language_profile import load_language_profile
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


def load_prompt_template(template_path: str) -> str:
    """加载 prompt 模板文件"""
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class AutoMethodUnderstander:
    """Auto 方法理解器 - 生成 MethodProfile"""
    
    def __init__(self, config: Config | None = None):
        """初始化"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # Load language profile for business annotations/decorators
        self.profile = load_language_profile(config=self.config)
        logger.info(f"Loaded language profile: {self.profile.language}")
        
        # 从配置读取参数
        self.max_methods = self.config.get(
            'method_understanding.max_methods',
            self.config.get('auto.max_methods', 50),
        )
        self.max_context_chars = self.config.get('generation.max_context_chars', 16000)
        
        # 加载 prompt 模板
        template_path = self.config.get(
            'prompts.method_understanding',
            'configs/prompts/auto_method_understanding.txt'
        )
        self.prompt_template = load_prompt_template(template_path)
        
        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.method_profiles_jsonl',
            'data/intermediate/method_profiles.jsonl'
        ))
        self.rejected_jsonl = Path(self.config.get(
            'artifacts.auto_method_understanding_rejected_jsonl',
            'data/intermediate/auto_method_understanding_rejected.jsonl'
        ))
        
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计
        self.stats = {
            'total_processed': 0,
            'success': 0,
            'failed': 0,
        }
    
    def generate_from_symbols(
        self,
        symbols_path: Path,
        repo_commit: str
    ) -> list[MethodProfile]:
        """从 symbols.jsonl 生成 method profiles
        
        Args:
            symbols_path: symbols.jsonl 文件路径
            repo_commit: 仓库 commit hash
            
        Returns:
            list[MethodProfile]: 成功生成的 profiles
        """
        logger.info(f"Loading symbols from {symbols_path}")
        
        # 读取所有符号
        symbols = []
        with open(symbols_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    symbol_dict = json.loads(line)
                    symbols.append(CodeSymbol(**symbol_dict))
        
        logger.info(f"Loaded {len(symbols)} symbols")
        
        # 选择候选方法
        candidates = self._select_candidates(symbols)
        logger.info(f"Selected {len(candidates)} candidate methods")
        
        # 生成 profiles
        profiles = []
        with open(self.output_jsonl, 'w', encoding='utf-8') as f_out, \
             open(self.rejected_jsonl, 'w', encoding='utf-8') as f_rej:
            
            for i, symbol in enumerate(candidates, 1):
                logger.info(f"Processing {i}/{len(candidates)}: {symbol.qualified_name}")
                
                try:
                    profile = self._generate_profile(symbol, repo_commit)
                    
                    # 写入成功的 profile
                    f_out.write(profile.model_dump_json() + '\n')
                    f_out.flush()
                    
                    profiles.append(profile)
                    self.stats['success'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to generate profile for {symbol.symbol_id}: {e}")
                    
                    # 写入失败记录
                    rejected_entry = {
                        'symbol_id': symbol.symbol_id,
                        'qualified_name': symbol.qualified_name,
                        'error': str(e),
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
                    }
                    f_rej.write(json.dumps(rejected_entry, ensure_ascii=False) + '\n')
                    f_rej.flush()
                    
                    self.stats['failed'] += 1
                
                self.stats['total_processed'] += 1
        
        logger.info(f"Profile generation completed: {self.stats['success']} success, {self.stats['failed']} failed")
        return profiles
    
    def _select_candidates(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """选择候选方法（复用 QA 选择候选逻辑）"""
        # 只选择方法符号
        methods = [s for s in symbols if s.symbol_type == 'method']
        
        # 计算优先级分数
        scored = []
        for symbol in methods:
            score = self._calculate_priority_score(symbol)
            scored.append((score, symbol))
        
        # 按分数降序排序
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # 取 Top-K
        selected = [s for _, s in scored[:self.max_methods]]
        return selected
    
    def _calculate_priority_score(self, symbol: CodeSymbol) -> int:
        """计算方法的优先级分数"""
        score = 0
        
        # Get business markers from language profile
        qa_markers = self.profile.get_qa_markers()
        business_annotations = set(qa_markers.get('annotations', []))
        business_decorators = set(qa_markers.get('decorators', []))
        
        # 业务注解/装饰器加分
        for ann in symbol.annotations:
            if ann.name in business_annotations or ann.name in business_decorators:
                score += 10
        
        # 有文档加分
        if symbol.doc:
            score += 5
        
        # 代码行数适中加分（太短或太长都不好）
        line_count = symbol.line_count
        if 10 <= line_count <= 100:
            score += 5
        elif 5 <= line_count < 10:
            score += 2
        
        return score
    
    def _generate_profile(
        self,
        symbol: CodeSymbol,
        repo_commit: str
    ) -> MethodProfile:
        """为单个方法生成 profile"""
        # 构造 prompt
        annotations_text = ", ".join([f"@{ann.name}" for ann in symbol.annotations])
        if not annotations_text:
            annotations_text = "无"
        
        javadoc_text = symbol.doc if symbol.doc else "无"
        
        # 截断源码
        source_code = symbol.source
        if len(source_code) > self.max_context_chars:
            source_code = source_code[:self.max_context_chars] + "\n... (源码已截断)"
        
        prompt = self.prompt_template.format(
            symbol_id=symbol.symbol_id,
            file_path=symbol.file_path,
            qualified_name=symbol.qualified_name,
            annotations=annotations_text,
            javadoc=javadoc_text,
            source_code=source_code,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            source_hash=symbol.source_hash,
            repo_commit=repo_commit
        )
        
        # 调用 LLM
        system_prompt = "你是一位资深的 Java 代码分析专家，擅长提取方法的业务语义和架构特征。"
        
        try:
            # 这里直接调用 LLM，期望返回 JSON
            response = self.llm_client.llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
            
            raw_output = response.content.strip()
            
            # 清理输出
            cleaned_output = self._clean_json_output(raw_output)
            
            # 解析为字典
            profile_dict = json.loads(cleaned_output)
            
            # 转换 evidence_refs
            evidence_refs = []
            for ref in profile_dict.get('evidence_refs', []):
                evidence_refs.append(EvidenceRef(**ref))
            profile_dict['evidence_refs'] = evidence_refs
            
            # 创建 MethodProfile
            profile = MethodProfile(**profile_dict)
            
            return profile
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _clean_json_output(self, output: str) -> str:
        """清理 LLM 输出，提取纯 JSON"""
        output = output.strip()
        
        # 移除 Markdown 代码块标记
        if output.startswith("```json"):
            output = output[7:]
        elif output.startswith("```"):
            output = output[3:]
        
        if output.endswith("```"):
            output = output[:-3]
        
        output = output.strip()
        
        # 查找第一个 { 和最后一个 }
        start_idx = output.find("{")
        end_idx = output.rfind("}")
        
        if start_idx != -1 and end_idx != -1:
            output = output[start_idx:end_idx+1]
        
        return output
    
    def print_summary(self):
        """打印统计摘要"""
        logger.info("=" * 60)
        logger.info("Method Understanding Summary")
        logger.info("=" * 60)
        logger.info(f"Total Processed: {self.stats['total_processed']}")
        logger.info(f"Success: {self.stats['success']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Output: {self.output_jsonl}")
        logger.info(f"Rejected: {self.rejected_jsonl}")
