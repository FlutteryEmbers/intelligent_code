"""
Auto 模块 - 答案生成器

基于问题和检索的上下文生成最终的 TrainingSample。
"""
import json
from pathlib import Path
from typing import List

from src.utils.schemas import QuestionSample, TrainingSample, CodeSymbol, EvidenceRef, ReasoningTrace
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils import vector_index
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


def load_prompt_template(template_path: str) -> str:
    """加载 prompt 模板文件"""
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class AutoAnswerGenerator:
    """Auto 答案生成器"""
    
    def __init__(self, config: Config | None = None):
        """初始化"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # 从配置读取参数
        self.top_k_context = self.config.get('auto.top_k_context', 6)
        self.max_context_chars = 16000  # Auto answer generation uses fixed context limit
        self.embedding_model = self.config.get('auto.embedding_model', 'nomic-embed-text')
        
        # 加载 prompt 模板
        template_path = self.config.get(
            'auto.prompts.answer_generation',
            'configs/prompts/auto_answer_generation.txt'
        )
        self.prompt_template = load_prompt_template(template_path)
        
        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'auto.outputs.auto_qa_raw_jsonl',
            'data/intermediate/auto_qa_raw.jsonl'
        ))
        self.rejected_jsonl = Path(self.config.get(
            'auto.outputs.auto_answer_rejected_jsonl',
            'data/intermediate/auto_answer_rejected.jsonl'
        ))
        self.embeddings_jsonl = Path(self.config.get(
            'auto.outputs.embeddings_jsonl',
            'data/intermediate/method_embeddings.jsonl'
        ))
        
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        
        # 统计
        self.stats = {
            'total_questions': 0,
            'success': 0,
            'failed': 0,
        }
    
    def generate_from_questions(
        self,
        questions_jsonl: Path,
        symbols_map: dict[str, CodeSymbol],
        repo_commit: str = "UNKNOWN_COMMIT"
    ) -> List[TrainingSample]:
        """从问题生成答案
        
        Args:
            questions_jsonl: questions.jsonl 文件路径
            symbols_map: symbol_id -> CodeSymbol 映射
            repo_commit: 仓库 commit hash
            
        Returns:
            List[TrainingSample]: 生成的训练样本列表
        """
        logger.info(f"Loading questions from {questions_jsonl}")
        
        # 读取所有问题
        questions = []
        with open(questions_jsonl, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    q_dict = json.loads(line)
                    # 转换 evidence_refs
                    evidence_refs = []
                    for ref in q_dict.get('evidence_refs', []):
                        evidence_refs.append(EvidenceRef(**ref))
                    q_dict['evidence_refs'] = evidence_refs
                    
                    questions.append(QuestionSample(**q_dict))
        
        logger.info(f"Loaded {len(questions)} questions")
        self.stats['total_questions'] = len(questions)
        
        # 为每个问题生成答案
        samples = []
        with open(self.output_jsonl, 'w', encoding='utf-8') as f_out, \
             open(self.rejected_jsonl, 'w', encoding='utf-8') as f_rej:
            
            for i, question in enumerate(questions, 1):
                logger.info(f"Generating answer for {i}/{len(questions)}: {question.question[:60]}...")
                
                try:
                    sample = self._generate_answer(question, symbols_map)
                    
                    # 写入成功的样本
                    f_out.write(sample.model_dump_json() + '\n')
                    f_out.flush()
                    
                    samples.append(sample)
                    self.stats['success'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to generate answer for question {question.question_id}: {e}")
                    
                    # 写入失败记录
                    rejected_entry = {
                        'question_id': question.question_id,
                        'question': question.question,
                        'error': str(e),
                        'timestamp': question.created_at
                    }
                    f_rej.write(json.dumps(rejected_entry, ensure_ascii=False) + '\n')
                    f_rej.flush()
                    
                    self.stats['failed'] += 1
        
        logger.info(f"Answer generation completed: {self.stats['success']} success, {self.stats['failed']} failed")
        return samples
    
    def _generate_answer(
        self,
        question: QuestionSample,
        symbols_map: dict[str, CodeSymbol]
    ) -> TrainingSample:
        """为单个问题生成答案"""
        # 1. 使用向量检索获取相关方法
        search_results = vector_index.search(
            query_text=question.question,
            embeddings_jsonl=self.embeddings_jsonl,
            embedding_model=self.embedding_model,
            top_k=self.top_k_context
        )
        
        if not search_results:
            raise ValueError("No relevant methods found in vector search")
        
        # 2. 构造上下文
        context_parts = []
        available_evidence = []
        total_chars = 0
        
        for symbol_id, score in search_results:
            symbol = symbols_map.get(symbol_id)
            if not symbol:
                continue
            
            # 检查是否超过最大长度
            if total_chars + len(symbol.source) > self.max_context_chars:
                break
            
            context_parts.append(f"// Method: {symbol.qualified_name}")
            context_parts.append(f"// Relevance Score: {score:.4f}")
            context_parts.append(symbol.source)
            context_parts.append("")  # 空行分隔
            
            total_chars += len(symbol.source)
            
            # 添加到可用证据列表
            available_evidence.append({
                'symbol_id': symbol.symbol_id,
                'file_path': symbol.file_path,
                'start_line': symbol.start_line,
                'end_line': symbol.end_line,
                'source_hash': symbol.source_hash
            })
        
        context = "\n".join(context_parts)
        
        # 3. 格式化可用证据引用
        available_evidence_text = json.dumps(available_evidence, indent=2, ensure_ascii=False)
        
        # 4. 构造 prompt
        prompt = self.prompt_template.format(
            question=question.question,
            context=context,
            available_evidence_refs=available_evidence_text,
            repo_commit=question.repo_commit
        )
        
        # 5. 调用 LLM
        system_prompt = "你是一位资深的 Java 架构师和代码审查专家，擅长基于代码证据进行深度分析。"
        
        try:
            response = self.llm_client.llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
            
            raw_output = response.content.strip()
            
            # 清理输出
            cleaned_output = self._clean_json_output(raw_output)
            
            # 解析为字典
            sample_dict = json.loads(cleaned_output)
            
            # 转换 thought
            thought_dict = sample_dict.get('thought', {})
            evidence_refs = []
            for ref in thought_dict.get('evidence_refs', []):
                evidence_refs.append(EvidenceRef(**ref))
            thought_dict['evidence_refs'] = evidence_refs
            
            reasoning_trace = ReasoningTrace(**thought_dict)
            sample_dict['thought'] = reasoning_trace
            
            # 确保 repo_commit 存在
            if 'repo_commit' not in sample_dict:
                sample_dict['repo_commit'] = question.repo_commit
            
            # 创建 TrainingSample
            sample = TrainingSample(**sample_dict)
            
            return sample
            
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
        logger.info("Answer Generation Summary")
        logger.info("=" * 60)
        logger.info(f"Total Questions: {self.stats['total_questions']}")
        logger.info(f"Success: {self.stats['success']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Output: {self.output_jsonl}")
        logger.info(f"Rejected: {self.rejected_jsonl}")
