"""
答案生成器

基于问题和检索的上下文生成最终的 TrainingSample。
"""
import json
from pathlib import Path
from typing import List

from src.utils.schemas import QuestionSample, TrainingSample, CodeSymbol, EvidenceRef, ReasoningTrace
from src.utils.config import Config
from src.utils.logger import get_logger
from src.utils.validator import normalize_path_separators
from src.utils.language_profile import load_language_profile
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


class AnswerGenerator:
    """答案生成器"""
    
    def __init__(self, config: Config | None = None):
        """初始化"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # Load language profile
        self.profile = load_language_profile(config=self.config)
        self.language = self.profile.language
        logger.info(f"Loaded language profile: {self.language}")
        
        # 从配置读取参数
        self.top_k_context = self.config.get(
            'core.retrieval_top_k',
            self.config.get('generation.retrieval_top_k', 6),
        )
        self.max_context_chars = self.config.get(
            'core.max_context_chars',
            self.config.get('generation.max_context_chars', 16000),
        )
        self.batch_size = self.config.get('question_answer.batch_size', None)
        self.embedding_model = self.config.get('question_answer.embedding_model', 'nomic-embed-text')
        
        # 加载 prompt 模板
        template_path = self.config.get(
            'prompts.question_answer.answer_generation',
            'configs/prompts/auto_answer_generation.txt'
        )
        self.prompt_template = load_prompt_template(template_path)
        
        # 输出路径
        self.output_jsonl = Path(self.config.get(
            'artifacts.auto_qa_raw_jsonl',
            'data/intermediate/auto_qa_raw.jsonl'
        ))
        self.rejected_jsonl = Path(self.config.get(
            'artifacts.auto_answer_rejected_jsonl',
            'data/intermediate/rejected/auto_answer_rejected.jsonl'
        ))
        self.embeddings_jsonl = Path(self.config.get(
            'artifacts.method_embeddings_jsonl',
            'data/intermediate/method_embeddings.jsonl'
        ))
        
        self.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        self.rejected_jsonl.parent.mkdir(parents=True, exist_ok=True)
        
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
        self.embeddings_available = self.embeddings_jsonl.exists()
        if not self.embeddings_available:
            logger.warning(
                "Embeddings file not found: %s (vector search disabled)",
                self.embeddings_jsonl,
            )
            missing_refs = sum(1 for q in questions if not q.evidence_refs)
            if missing_refs:
                logger.warning(
                    "Questions missing evidence_refs: %s (provide evidence_refs or enable auto mode)",
                    missing_refs,
                )
        
        # 为每个问题生成答案
        samples = []
        with open(self.output_jsonl, 'w', encoding='utf-8') as f_out, \
             open(self.rejected_jsonl, 'w', encoding='utf-8') as f_rej:
            
            batch_size = self.batch_size or len(questions) or 1
            for batch_start in range(0, len(questions), batch_size):
                batch = questions[batch_start:batch_start + batch_size]
                if self.batch_size:
                    logger.info(
                        "Answer batch %s-%s/%s",
                        batch_start + 1,
                        batch_start + len(batch),
                        len(questions),
                    )
                for i, question in enumerate(batch, batch_start + 1):
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
                        logger.error(f"Exception type: {type(e).__name__}")
                        logger.error(f"Full traceback:", exc_info=True)
                        
                        # 写入失败记录
                        rejected_entry = {
                            'question_id': question.question_id,
                            'question': question.question,
                            'error': str(e),
                            'error_type': type(e).__name__,
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
        # 1. 构造上下文（优先使用问题自带的 evidence_refs）
        context_parts = []
        available_evidence = []
        total_chars = 0

        if question.evidence_refs:
            for ref in question.evidence_refs:
                # 标准化路径以支持跨平台
                normalized_symbol_id = normalize_path_separators(ref.symbol_id)
                symbol = symbols_map.get(normalized_symbol_id)
                if not symbol:
                    continue

                if total_chars + len(symbol.source) > self.max_context_chars:
                    break

                context_parts.append(f"// Method: {symbol.qualified_name}")
                context_parts.append(symbol.source)
                context_parts.append("")  # 空行分隔

                total_chars += len(symbol.source)

                available_evidence.append({
                    'symbol_id': symbol.symbol_id,
                    'file_path': symbol.file_path,
                    'start_line': symbol.start_line,
                    'end_line': symbol.end_line,
                    'source_hash': symbol.source_hash
                })

        # 2. 如果缺少 evidence_refs 或未找到上下文，回退到向量检索
        if not context_parts:
            if not self.embeddings_available:
                raise ValueError(
                    "Embeddings not found for vector search. Provide evidence_refs in user_questions.yaml, "
                    "enable auto mode, or set question_answer.build_embeddings_in_user_mode=true."
                )
            search_results = vector_index.search(
                query_text=question.question,
                embeddings_jsonl=self.embeddings_jsonl,
                embedding_model=self.embedding_model,
                top_k=self.top_k_context
            )

            if not search_results:
                raise ValueError("No relevant methods found in vector search")

            for symbol_id, score in search_results:
                # 标准化路径以支持跨平台
                normalized_symbol_id = normalize_path_separators(symbol_id)
                symbol = symbols_map.get(normalized_symbol_id)
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
        
        # 4. 从language profile获取格式约束
        answer_gen_config = self.profile.get('answer_generation', {})
        format_constraints = answer_gen_config.get('format_constraints', '')
        
        # 5. 格式化常见错误示例
        common_mistakes = answer_gen_config.get('common_mistakes', [])
        mistakes_text = self._format_common_mistakes(common_mistakes)
        
        # 6. 构造 prompt
        prompt = self.prompt_template.format(
            question=question.question,
            context=context,
            available_evidence_refs=available_evidence_text,
            repo_commit=question.repo_commit,
            format_constraints=format_constraints,
            common_mistakes_examples=mistakes_text
        )
        
        # 7. 调用 LLM
        language_display = self.language.capitalize()
        system_prompt = f"你是一位资深的 {language_display} 架构师和代码审查专家，擅长基于代码证据进行深度分析。"
        
        try:
            response = self.llm_client.llm.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.llm_client.max_tokens
            )
            
            raw_output = response.content.strip()
            
            # 调试：保存原始输出到文件
            debug_file = Path("data/intermediate/rejected/llm_answer_raw_output.txt")
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"Question: {question.question[:80]}\n")
                f.write(f"Raw Output:\n{raw_output}\n")
            
            # 清理输出
            cleaned_output = self._clean_json_output(raw_output)
            
            # 调试：保存清理后的输出
            with open(debug_file, 'a', encoding='utf-8') as f:
                f.write(f"Cleaned Output:\n{cleaned_output}\n")
            
            # 解析为字典
            try:
                sample_dict = json.loads(cleaned_output)
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON parsing failed: {json_err}")
                logger.error(f"Cleaned output that failed to parse: {cleaned_output[:500]}")
                raise ValueError(f"Invalid JSON from LLM: {json_err}") from json_err

            # 只读取最小结构：answer + thought
            answer_value = sample_dict.get("answer")
            if answer_value is None:
                logger.error("Answer field is missing from LLM output!")
                raise ValueError("LLM output missing 'answer' field")
            if isinstance(answer_value, dict):
                logger.warning(
                    "Answer field is dict with keys: %s, converting to string",
                    list(answer_value.keys()),
                )
                answer_parts = []

                # 常见的中文键
                key_order = ['结论', '结论性陈述', '机制', '机制说明', '规则说明', '注意事项', '风险点']

                # 按顺序处理已知键
                for key in key_order:
                    if key in answer_value:
                        value = answer_value[key]
                        if isinstance(value, list):
                            value = '\n'.join(f"- {item}" for item in value)
                        answer_parts.append(f"**{key}**:\n{value}")

                # 处理其他未知键
                for key, value in answer_value.items():
                    if key not in key_order:
                        if isinstance(value, list):
                            value = '\n'.join(f"- {item}" for item in value)
                        answer_parts.append(f"**{key}**:\n{value}")

                answer_value = '\n\n'.join(answer_parts)
                logger.info("Converted answer to string, length: %s", len(answer_value))
            elif not isinstance(answer_value, str):
                logger.warning("Answer field is %s, converting to string", type(answer_value))
                answer_value = str(answer_value)

            thought_dict = sample_dict.get("thought")
            if not isinstance(thought_dict, dict):
                raise ValueError("LLM output missing 'thought' object")
            for key in ("observations", "inferences", "assumptions"):
                if key not in thought_dict or not isinstance(thought_dict[key], list):
                    thought_dict[key] = []
            raw_refs = thought_dict.get("evidence_refs", [])
            if not isinstance(raw_refs, list) or not raw_refs:
                raise ValueError("LLM output missing thought.evidence_refs")
            evidence_refs = []
            for ref in raw_refs:
                evidence_refs.append(EvidenceRef(**ref))
            thought_dict["evidence_refs"] = evidence_refs
            reasoning_trace = ReasoningTrace(**thought_dict)

            # 创建 TrainingSample（其余字段由系统填充）
            sample = TrainingSample(
                scenario="qa_rule",
                instruction=question.question,
                context=context,
                thought=reasoning_trace,
                answer=answer_value,
                repo_commit=question.repo_commit,
            )
            
            return sample
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _format_common_mistakes(self, mistakes: list) -> str:
        """格式化常见错误示例"""
        if not mistakes:
            return ""
        
        parts = []
        for i, mistake in enumerate(mistakes, 1):
            parts.append(f"### 错误 {i}: {mistake.get('description', '')}")
            parts.append("\n❌ **错误示例**:")
            parts.append("```json")
            parts.append(mistake.get('wrong', ''))
            parts.append("```")
            parts.append("\n✅ **正确示例**:")
            parts.append("```json")
            parts.append(mistake.get('correct', ''))
            parts.append("```")
            parts.append("")
        
        return "\n".join(parts)
    
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
