import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml
from src.schemas import CodeSymbol, TrainingSample, ReasoningTrace, EvidenceRef
from src.utils.core.config import Config
from src.utils.core.logger import get_logger
from src.utils.data.validator import normalize_path_separators
from src.utils.data.sampling import sample_negative_type
from src.utils.generation.config_helpers import (
    parse_coverage_config, parse_constraints_config,
    parse_output_paths, create_seeded_rng, get_with_fallback,
)
from src.utils.io.file_ops import (
    load_yaml_file, read_jsonl, append_jsonl, write_json
)
from src.utils.io.loaders import load_symbols_jsonl
from src.engine.core import BaseGenerator
from src.engine.rag import Retriever

logger = get_logger(__name__)

class DesignQuestion:
    """设计问题模型"""
    def __init__(
        self,
        id: str,
        goal: str,
        constraints: List[str],
        acceptance_criteria: List[str],
        non_goals: Optional[List[str]] = None,
        question_type: Optional[str] = None
    ):
        self.id = id
        self.goal = goal
        self.constraints = constraints
        self.acceptance_criteria = acceptance_criteria
        self.non_goals = non_goals or []
        self.question_type = question_type or "architecture"
    
    def to_dict(self):
        return {
            'id': self.id,
            'goal': self.goal,
            'constraints': self.constraints,
            'acceptance_criteria': self.acceptance_criteria,
            'non_goals': self.non_goals,
            'question_type': self.question_type,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DesignQuestion':
        return cls(
            id=data['id'],
            goal=data['goal'],
            constraints=data.get('constraints', []),
            acceptance_criteria=data.get('acceptance_criteria', []),
            non_goals=data.get('non_goals', []),
            question_type=data.get('question_type'),
        )

def load_design_questions_config(config_path: str | Path | None = None) -> List[DesignQuestion]:
    """从 YAML 加载设计问题"""
    if config_path is None:
        config_path = Path("configs/user_inputs/design_questions.yaml")
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        return []
    
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
        
    return [DesignQuestion.from_dict(q) for q in data.get('design_questions', [])]

class DesignGenerator(BaseGenerator):
    """
    架构设计方案生成器 - 继承自 BaseGenerator
    
    职责：
    1. 基于设计问题生成完整方案。
    2. 利用层级平衡的 Retriever 获取上下文。
    3. 支持 6 章节架构设计输出规范。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """初始化"""
        super().__init__(scenario="arch_design", config=config)
        
        # 1. 核心组件
        self.profile = self._get_language_profile()
        self.retriever = Retriever(self.config, self.profile)
        
        # 2. 配置解析
        self.max_samples = self.config.get('core.max_items', 50)
        self.coverage_cfg = parse_coverage_config(self.config, 'design_questions')
        self.constraints_cfg = parse_constraints_config(self.config, 'design_questions')
        self.negative_rng = create_seeded_rng(self.config)
        
        # 3. 输出路径
        self.output_dir = Path(self.config.get('output.intermediate_dir', 'data/intermediate'))
        self.raw_output_path = self.output_dir / 'design_raw.jsonl'
        self.rejected_path = Path(self.config.get('artifacts.design_rejected_jsonl', self.output_dir / 'rejected' / 'design_rejected.jsonl'))
        
        # 4. 负向采样规则
        negative_rules_path = Path("configs/prompts/qa_rule/negative_rules.yaml") # 共享 QA 的负向规则结构
        self.negative_rules_map = load_yaml_file(str(negative_rules_path)) if negative_rules_path.exists() else {}

        # 5. 统计
        self.stats = {'total': 0, 'success': 0, 'failed': 0}
        self.retrieval_stats = {"negative_samples": 0, "positive_samples": 0}

    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: Optional[str] = None,
        design_questions: Optional[List[DesignQuestion]] = None
    ) -> List[TrainingSample]:
        """批量生成流程"""
        logger.info(f"Starting design generation from {symbols_path}")
        symbols = load_symbols_jsonl(symbols_path)
        if not symbols: return []
        
        if not repo_commit:
            repo_commit = symbols[0].repo_commit
            
        if design_questions is None:
            design_questions = load_design_questions_config()
            
        # 限制数量
        if len(design_questions) > self.max_samples:
            design_questions = design_questions[:self.max_samples]
            
        self.stats['total'] = len(design_questions)
        samples = []
        
        self.config.ensure_output_dirs()
        with open(self.raw_output_path, 'w', encoding='utf-8') as f_out, \
             open(self.rejected_path, 'w', encoding='utf-8') as f_rej:
             
            for i, q in enumerate(design_questions, 1):
                logger.info(f"[{i}/{len(design_questions)}] Designing for: {q.id}")
                
                try:
                    negative_type = self._sample_negative_type()
                    if negative_type: self.retrieval_stats["negative_samples"] += 1
                    else: self.retrieval_stats["positive_samples"] += 1
                    
                    sample = self._generate_single(q, symbols, repo_commit, negative_type)
                    if sample:
                        f_out.write(sample.model_dump_json() + '\n')
                        f_out.flush()
                        samples.append(sample)
                        self.stats['success'] += 1
                    else:
                        self.stats['failed'] += 1
                        
                except Exception as e:
                    logger.error(f"Design failed for {q.id}: {e}", exc_info=True)
                    f_rej.write(json.dumps({'id': q.id, 'error': str(e)}, ensure_ascii=False) + '\n')
                    self.stats['failed'] += 1
                    
        self._write_retrieval_report()
        return samples

    def _generate_single(self, q: DesignQuestion, symbols: List[CodeSymbol], repo_commit: str, negative_type: Optional[str]) -> Optional[TrainingSample]:
        """单个设计生成逻辑"""
        # 1. RAG
        relevant_symbols = self.retriever.retrieve_relevant_symbols(q.goal, symbols)
        if not relevant_symbols: return None
        
        # 2. 构造上下文 (保持原有的层级分组格式)
        context = self._build_grouped_context(relevant_symbols)
        
        # 3. 准备提示词内容
        controller = next((s for s in relevant_symbols if self.profile.is_controller(s)), relevant_symbols[0])
        service = next((s for s in relevant_symbols if self.profile.is_service(s)), None)
        
        # Service/Primary evidence 辅助块
        # 如果没有 Service，降级使用 Controller 或任一相关符号作为主要证据
        primary_symbol = service or controller or (relevant_symbols[0] if relevant_symbols else None)
        
        service_evidence = ""
        service_evidence_json = ""
        if primary_symbol:
            norm_path = normalize_path_separators(primary_symbol.file_path)
            norm_id = normalize_path_separators(primary_symbol.symbol_id)
            # JSON 块直接包含在 evidence 文本中，方便 LLM 复制
            evidence_json_block = json.dumps({
                "symbol_id": norm_id,
                "file_path": norm_path,
                "start_line": primary_symbol.start_line,
                "end_line": primary_symbol.end_line,
                "source_hash": primary_symbol.source_hash
            }, ensure_ascii=False)
            
            service_evidence = (
                f"\n核心组件证据 (Reference Evidence):\n"
                f"- symbol_id: \"{norm_id}\"\n"
                f"- file_path: \"{norm_path}\"\n"
                f"- start_line: {primary_symbol.start_line}\n"
                f"- end_line: {primary_symbol.end_line}\n"
                f"\n请在 answer 和 thought.evidence_refs 中引用以下元数据：\n"
                f"```json\n{evidence_json_block}\n```\n"
            )
            # 保留 json 变量以防万一
            service_evidence_json = f",\n      {evidence_json_block}"

        # 4. 组装提示词
        system_prompt = self._build_composed_system_prompt()
        user_prompt = self._build_composed_user_prompt(
            "gen_s_user",
            design_question_id=q.id,
            goal=q.goal,
            constraints='\n'.join([f'- {c}' for c in q.constraints]),
            acceptance_criteria='\n'.join([f'- {a}' for a in q.acceptance_criteria]),
            non_goals='\n'.join([f'- {n}' for n in q.non_goals]),
            context=context,
            controller_symbol_id=normalize_path_separators(controller.symbol_id),
            controller_file_path=normalize_path_separators(controller.file_path),
            controller_start_line=controller.start_line,
            controller_end_line=controller.end_line,
            controller_source_hash=controller.source_hash,
            service_evidence=service_evidence,
            service_evidence_json=service_evidence_json,
            goal_short=q.goal[:50],
            repo_commit=repo_commit,
            architecture_constraints=self._format_architecture_constraints(),
            counterexample_guidance=self._format_counterexample_guidance()
        )
        
        if negative_type:
            user_prompt = self._inject_negative_rules(user_prompt, negative_type)
            
        # 5. LLM 调用
        output_dict = self.generate_with_retry(system_prompt, user_prompt)
        
        # 6. 解析转换
        answer = output_dict.get("answer", "")
        if isinstance(answer, dict): 
            answer = json.dumps(answer, ensure_ascii=False)
            
        thought_data = output_dict.get("thought", {})
        raw_refs = thought_data.get("evidence_refs", [])
        thought_data["evidence_refs"] = self._correct_evidence_refs(raw_refs, relevant_symbols)
        
        quality = {
            "coverage": {
                "polarity": "negative" if negative_type else "positive",
                "question_type": q.question_type or "architecture",
                "negative_type": negative_type
            }
        }
        
        return TrainingSample(
            scenario="arch_design",
            instruction=q.goal,
            context=context,
            thought=ReasoningTrace(**thought_data),
            answer=answer,
            repo_commit=repo_commit,
            quality=quality
        )

    def _build_grouped_context(self, symbols: List[CodeSymbol]) -> str:
        """保持原有的架构分组上下文格式，并支持未分类组件"""
        parts = []
        lang = self.profile.language
        
        # Track which symbols are already added
        added_ids = set()
        
        for layer in ['controller', 'service', 'repository']:
            layer_symbols = self.profile.filter_by_layer(symbols, layer)
            if not layer_symbols: continue
            
            parts.append(f"\n# {layer.capitalize()} 层")
            for s in layer_symbols:
                if s.symbol_id in added_ids: continue
                parts.append(f"## {s.qualified_name} (File: {normalize_path_separators(s.file_path)} Lines: {s.start_line}-{s.end_line})\n```{lang}\n{s.source[:800]}\n```")
                added_ids.add(s.symbol_id)
                
        # Handle unclassified symbols
        other_symbols = [s for s in symbols if s.symbol_id not in added_ids]
        if other_symbols:
            parts.append("\n# Other Components")
            for s in other_symbols:
                parts.append(f"## {s.qualified_name} (File: {normalize_path_separators(s.file_path)} Lines: {s.start_line}-{s.end_line})\n```{lang}\n{s.source[:800]}\n```")

        return "\n".join(parts)

    def _sample_negative_type(self) -> Optional[str]:
        return sample_negative_type(self.coverage_cfg.negative_ratio, self.coverage_cfg.negative_types, self.negative_rng)

    def _inject_negative_rules(self, prompt: str, negative_type: str) -> str:
        rules = self.negative_rules_map.get(negative_type, [])
        if not rules: return prompt
        rules_text = "\n".join(f"- {r}" for r in rules)
        negative_instruction = f"\n\n## 负向采样要求 ({negative_type})\n{rules_text}\n"
        return prompt.replace("# 输出要求", f"{negative_instruction}\n# 输出要求") if "# 输出要求" in prompt else prompt + negative_instruction

    def _format_architecture_constraints(self) -> str:
        constraints = self.constraints_cfg.architecture_constraints or []
        return "\n".join(f"- {c}" for c in constraints) if constraints else "无"

    def _format_counterexample_guidance(self) -> str:
        return "请在回答中包含 'Rejected Alternatives' 部分。" if self.constraints_cfg.enable_counterexample else ""

    def _correct_evidence_refs(self, raw_refs: List[Dict], symbols: List[CodeSymbol]) -> List[EvidenceRef]:
        """Correlate LLM evidence refs with trusted symbols"""
        corrected = []
        for ref in raw_refs:
            if not isinstance(ref, dict): 
                corrected.append(ref)
                continue
                
            ref_id = ref.get('symbol_id', '')
            best_match = None
            
            norm_ref_id = normalize_path_separators(ref_id)
            for s in symbols:
                if normalize_path_separators(s.symbol_id) == norm_ref_id:
                    best_match = s
                    break
            
            if not best_match and ':' in ref_id:
                ref_prefix = ref_id.rsplit(':', 1)[0]
                norm_prefix = normalize_path_separators(ref_prefix)
                for s in symbols:
                    if normalize_path_separators(s.symbol_id).rsplit(':', 1)[0] == norm_prefix:
                        best_match = s
                        break
            
            if best_match:
                ref['symbol_id'] = normalize_path_separators(best_match.symbol_id)
                ref['file_path'] = normalize_path_separators(best_match.file_path)
                ref['start_line'] = best_match.start_line
                ref['end_line'] = best_match.end_line
                ref['source_hash'] = best_match.source_hash
            
            try:
                corrected.append(EvidenceRef(**ref))
            except Exception:
                corrected.append(ref) # Fallback
                
        return corrected

    def _write_retrieval_report(self):
        report_path = Path("data/reports/design_retrieval_stats.json")
        write_json(str(report_path), self.retrieval_stats)

    def print_summary(self):
        logger.info(f"Design Summary: {self.stats['success']} Succeeded, {self.stats['failed']} Failed")
