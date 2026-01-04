"""
场景 2：架构设计方案生成器 - 基于需求生成设计方案

从代码仓库中检索相关上下文，为给定需求生成架构设计方案。
"""
import json
import time
from pathlib import Path
from typing import Generator
from collections import Counter

from src.utils.schemas import CodeSymbol, TrainingSample, ReasoningTrace, EvidenceRef, sha256_text
from src.utils.config import Config
from src.utils.logger import get_logger
from src.engine.llm_client import LLMClient

logger = get_logger(__name__)


class Requirement:
    """需求模型"""
    def __init__(
        self,
        id: str,
        goal: str,
        constraints: list[str],
        acceptance_criteria: list[str],
        non_goals: list[str] | None = None
    ):
        self.id = id
        self.goal = goal
        self.constraints = constraints
        self.acceptance_criteria = acceptance_criteria
        self.non_goals = non_goals or []
    
    def to_dict(self):
        return {
            'id': self.id,
            'goal': self.goal,
            'constraints': self.constraints,
            'acceptance_criteria': self.acceptance_criteria,
            'non_goals': self.non_goals
        }


# 内置需求库
BUILT_IN_REQUIREMENTS = [
    Requirement(
        id="REQ-001",
        goal="为用户登录接口添加 Redis 缓存层，提升高并发场景下的性能",
        constraints=[
            "使用 Redis 作为缓存存储",
            "缓存有效期为 30 分钟",
            "需要保证缓存与数据库数据一致性",
            "需要支持缓存预热和失效策略"
        ],
        acceptance_criteria=[
            "登录 QPS 提升 5 倍以上",
            "缓存命中率 > 90%",
            "缓存穿透/雪崩有防护机制",
            "支持缓存手动刷新"
        ],
        non_goals=[
            "不改变现有登录业务逻辑",
            "不引入分布式锁（MVP 阶段）"
        ]
    ),
    Requirement(
        id="REQ-002",
        goal="为订单创建接口实现幂等性保证，防止重复下单",
        constraints=[
            "使用唯一业务流水号作为幂等标识",
            "幂等信息需要持久化",
            "幂等检查失败时返回明确错误",
            "支持幂等信息过期清理"
        ],
        acceptance_criteria=[
            "相同流水号的重复请求返回相同结果",
            "幂等检查响应时间 < 10ms",
            "幂等信息保留 24 小时",
            "支持幂等状态查询接口"
        ],
        non_goals=[
            "不处理分布式事务回滚",
            "不实现全局唯一 ID 生成器"
        ]
    ),
    Requirement(
        id="REQ-003",
        goal="为产品查询接口实现读写分离，提升查询性能",
        constraints=[
            "主库负责写操作，从库负责读操作",
            "需要处理主从延迟问题",
            "从库故障时自动切换到主库",
            "支持手动指定读主库"
        ],
        acceptance_criteria=[
            "读请求 > 95% 走从库",
            "主从延迟 < 1 秒",
            "从库故障切换时间 < 3 秒",
            "提供监控指标（主从延迟、读写比例）"
        ],
        non_goals=[
            "不实现自动主从切换（依赖 DBA）",
            "不支持多从库负载均衡（MVP 阶段）"
        ]
    ),
    Requirement(
        id="REQ-004",
        goal="为商品搜索接口添加限流保护，防止恶意刷单",
        constraints=[
            "基于用户 ID 和 IP 的双重限流",
            "使用令牌桶算法",
            "限流阈值可配置",
            "限流触发时返回 429 状态码"
        ],
        acceptance_criteria=[
            "单用户 QPS 限制在 10 次/秒",
            "单 IP QPS 限制在 100 次/秒",
            "限流信息存储在 Redis",
            "提供限流白名单功能"
        ],
        non_goals=[
            "不实现分布式限流（单机版）",
            "不记录限流日志到数据库"
        ]
    ),
    Requirement(
        id="REQ-005",
        goal="为用户收藏夹功能添加异步处理，优化响应时间",
        constraints=[
            "使用消息队列（RabbitMQ/Kafka）",
            "收藏操作立即返回，后台异步处理",
            "需要保证最终一致性",
            "失败重试 3 次"
        ],
        acceptance_criteria=[
            "接口响应时间 < 100ms",
            "消息处理成功率 > 99.9%",
            "失败消息进入死信队列",
            "提供收藏状态查询接口"
        ],
        non_goals=[
            "不实现消息顺序保证",
            "不支持事务消息（MVP 阶段）"
        ]
    ),
]


class DesignGenerator:
    """
    架构设计方案生成器
    
    为给定需求生成基于现有代码架构的设计方案：
    1. 需求结构化存储
    2. 轻量级 RAG（过滤 + 检索）
    3. LLM 生成设计方案
    4. 质量校验并保存
    """
    
    # 架构层级注解
    CONTROLLER_ANNOTATIONS = {'RestController', 'Controller'}
    SERVICE_ANNOTATIONS = {'Service', 'Component'}
    REPOSITORY_ANNOTATIONS = {'Repository'}
    
    # 架构层级关键词
    CONTROLLER_KEYWORDS = ['controller', 'endpoint', 'api', 'rest']
    SERVICE_KEYWORDS = ['service', 'manager', 'handler']
    REPOSITORY_KEYWORDS = ['repository', 'dao', 'mapper']
    ENTITY_KEYWORDS = ['entity', 'model', 'dto', 'vo']
    
    def __init__(self, config: Config | None = None):
        """初始化生成器"""
        self.config = config or Config()
        self.llm_client = LLMClient()
        
        # 从配置读取参数
        self.top_k_context = self.config.get('design_generator.top_k_context', 6)
        self.max_context_chars = self.config.get('design_generator.max_context_chars', 20000)
        self.max_samples = self.config.get('design_generator.max_samples', 10)
        
        # 输出路径
        self.output_dir = Path('data/intermediate')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.requirements_path = self.output_dir / 'requirements.jsonl'
        self.raw_output_path = self.output_dir / 'design_raw.jsonl'
        self.rejected_path = self.output_dir / 'design_rejected.jsonl'
        
        # 统计
        self.stats = {
            'total_requirements': 0,
            'generated_samples': 0,
            'rejected_samples': 0,
            'validation_errors': []
        }
        
        logger.info(f"DesignGenerator initialized with top_k={self.top_k_context}, max_context_chars={self.max_context_chars}")
    
    def generate_from_repo(
        self,
        symbols_path: str | Path = 'data/raw/extracted/symbols.jsonl',
        repo_commit: str | None = None,
        requirements: list[Requirement] | None = None
    ) -> list[TrainingSample]:
        """
        从符号文件和需求生成设计方案
        
        Args:
            symbols_path: 符号 JSONL 文件路径
            repo_commit: 仓库 commit
            requirements: 需求列表（可选，默认使用内置需求）
            
        Returns:
            list[TrainingSample]: 生成的训练样本列表
        """
        start_time = time.time()
        logger.info(f"Starting design generation from {symbols_path}")
        
        # 加载符号
        symbols = self._load_symbols(symbols_path)
        
        if not symbols:
            logger.warning("No symbols loaded")
            return []
        
        # 推断 repo_commit
        if not repo_commit:
            repo_commit = symbols[0].repo_commit
            logger.info(f"Using repo_commit from symbols: {repo_commit}")
        
        # 使用内置需求或自定义需求
        if requirements is None:
            requirements = BUILT_IN_REQUIREMENTS
        
        self.stats['total_requirements'] = len(requirements)
        
        # 保存需求到文件
        self._save_requirements(requirements)
        
        # 限制需求数量
        if len(requirements) > self.max_samples:
            logger.info(f"Limiting requirements to {self.max_samples} (from {len(requirements)})")
            requirements = requirements[:self.max_samples]
        
        # 为每个需求生成设计方案
        samples = []
        for i, req in enumerate(requirements, 1):
            logger.info(f"Processing requirement {i}/{len(requirements)}: {req.id}")
            
            try:
                sample = self._generate_single(req, symbols, repo_commit)
                if sample:
                    samples.append(sample)
                    self.stats['generated_samples'] += 1
            except Exception as e:
                logger.error(f"Failed to generate sample for {req.id}: {e}")
                self._log_rejected(req, str(e), None)
                self.stats['rejected_samples'] += 1
        
        # 保存结果
        self._save_samples(samples)
        
        elapsed = time.time() - start_time
        logger.info(f"Design generation completed in {elapsed:.1f}s:")
        logger.info(f"  - Total requirements: {self.stats['total_requirements']}")
        logger.info(f"  - Generated samples: {self.stats['generated_samples']}")
        logger.info(f"  - Rejected samples: {self.stats['rejected_samples']}")
        
        return samples
    
    def _load_symbols(self, symbols_path: Path | str) -> list[CodeSymbol]:
        """加载符号文件"""
        symbols_path = Path(symbols_path)
        
        if not symbols_path.exists():
            raise FileNotFoundError(f"Symbols file not found: {symbols_path}")
        
        symbols = []
        with open(symbols_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    symbol = CodeSymbol(**data)
                    symbols.append(symbol)
                except Exception as e:
                    logger.warning(f"Failed to parse symbol at line {line_num}: {e}")
        
        logger.info(f"Loaded {len(symbols)} symbols from {symbols_path}")
        return symbols
    
    def _save_requirements(self, requirements: list[Requirement]):
        """保存需求到 JSONL"""
        with open(self.requirements_path, 'w', encoding='utf-8') as f:
            for req in requirements:
                f.write(json.dumps(req.to_dict(), ensure_ascii=False) + '\n')
        
        logger.info(f"Saved {len(requirements)} requirements to {self.requirements_path}")
    
    def _generate_single(
        self,
        requirement: Requirement,
        symbols: list[CodeSymbol],
        repo_commit: str
    ) -> TrainingSample | None:
        """为单个需求生成设计方案"""
        # 1. RAG：检索相关上下文
        relevant_symbols = self._retrieve_context(requirement, symbols)
        
        if not relevant_symbols:
            logger.warning(f"No relevant symbols found for {requirement.id}")
            self._log_rejected(requirement, "No relevant context found", None)
            return None
        
        logger.info(f"Retrieved {len(relevant_symbols)} relevant symbols for {requirement.id}")
        
        # 2. 构造上下文
        context = self._build_context(relevant_symbols, requirement)
        
        # 3. 构造 prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(requirement, context, relevant_symbols, repo_commit)
        
        # 4. 调用 LLM
        try:
            sample = self.llm_client.generate_training_sample(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                scenario="arch_design",
                repo_commit=repo_commit
            )
        except Exception as e:
            logger.warning(f"LLM generation failed for {requirement.id}: {e}")
            self._log_rejected(requirement, f"LLM error: {e}", None)
            return None
        
        # 5. 强制设置必填字段
        sample.scenario = "arch_design"
        sample.repo_commit = repo_commit
        
        # 6. 校验样本
        is_valid, errors = self._validate_sample(sample, requirement, repo_commit, symbols)
        
        if not is_valid:
            logger.warning(f"Validation failed for {requirement.id}: {errors}")
            self._log_rejected(requirement, "Validation failed", {"errors": errors, "sample": sample.model_dump()})
            self.stats['validation_errors'].append({
                'requirement_id': requirement.id,
                'errors': errors
            })
            return None
        
        # 7. 添加质量标记
        sample.quality = {
            "schema_ok": True,
            "evidence_ok": True,
            "requirement_id": requirement.id,
            "context_symbols": len(relevant_symbols)
        }
        
        return sample
    
    def _retrieve_context(
        self,
        requirement: Requirement,
        symbols: list[CodeSymbol]
    ) -> list[CodeSymbol]:
        """
        轻量级 RAG：两段式检索
        
        1. 过滤：优先 Controller/Service/Repository
        2. 检索：关键词打分，返回 top_k
        """
        # 第一阶段：过滤候选
        candidates = self._filter_candidates(symbols)
        
        if not candidates:
            logger.warning("No candidates after filtering")
            return []
        
        logger.debug(f"Filtered to {len(candidates)} candidates")
        
        # 第二阶段：关键词检索打分
        scored_candidates = []
        
        # 提取需求关键词
        req_keywords = self._extract_keywords(requirement.goal)
        
        for symbol in candidates:
            score = self._calculate_relevance_score(symbol, req_keywords)
            if score > 0:
                scored_candidates.append((symbol, score))
        
        # 按分数排序
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 返回 top_k
        top_symbols = [s for s, _ in scored_candidates[:self.top_k_context]]
        
        # 确保包含不同层级
        top_symbols = self._balance_layers(top_symbols, candidates)
        
        return top_symbols
    
    def _filter_candidates(self, symbols: list[CodeSymbol]) -> list[CodeSymbol]:
        """过滤候选符号：优先 Controller/Service/Repository"""
        candidates = []
        
        for symbol in symbols:
            if symbol.symbol_type != 'method':
                continue
            
            # 检查注解
            annotations = {ann.name for ann in symbol.annotations}
            
            if annotations & (self.CONTROLLER_ANNOTATIONS | self.SERVICE_ANNOTATIONS | self.REPOSITORY_ANNOTATIONS):
                candidates.append(symbol)
                continue
            
            # 检查路径
            path_lower = symbol.file_path.lower()
            qualified_lower = symbol.qualified_name.lower()
            
            if any(kw in path_lower or kw in qualified_lower for kw in 
                   self.CONTROLLER_KEYWORDS + self.SERVICE_KEYWORDS + self.REPOSITORY_KEYWORDS):
                candidates.append(symbol)
        
        return candidates
    
    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词（简单版：分词 + 过滤停用词）"""
        # 简单分词
        words = text.lower().split()
        
        # 停用词
        stopwords = {'的', '了', '在', '是', '为', '和', '与', '或', '但', '等', 
                     'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        
        # 过滤
        keywords = [w for w in words if len(w) > 1 and w not in stopwords]
        
        return keywords
    
    def _calculate_relevance_score(self, symbol: CodeSymbol, req_keywords: list[str]) -> int:
        """计算符号与需求的相关性分数"""
        score = 0
        
        # 搜索范围：qualified_name + doc + source
        search_text = f"{symbol.qualified_name} {symbol.doc or ''} {symbol.source}".lower()
        
        # 关键词匹配
        for keyword in req_keywords:
            if keyword in search_text:
                score += 1
        
        # 注解加分
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.CONTROLLER_ANNOTATIONS:
            score += 3  # Controller 是入口，加分
        if annotations & self.SERVICE_ANNOTATIONS:
            score += 2  # Service 是核心逻辑
        
        # 有文档加分
        if symbol.doc:
            score += 1
        
        return score
    
    def _balance_layers(
        self,
        selected: list[CodeSymbol],
        all_candidates: list[CodeSymbol]
    ) -> list[CodeSymbol]:
        """平衡不同架构层级"""
        # 统计已选择的层级
        layers = {'controller': 0, 'service': 0, 'repository': 0}
        
        for symbol in selected:
            if self._is_controller(symbol):
                layers['controller'] += 1
            elif self._is_service(symbol):
                layers['service'] += 1
            elif self._is_repository(symbol):
                layers['repository'] += 1
        
        # 如果缺少 Controller，尝试补充
        if layers['controller'] == 0:
            for candidate in all_candidates:
                if self._is_controller(candidate) and candidate not in selected:
                    selected.insert(0, candidate)
                    break
        
        # 如果缺少 Service，尝试补充
        if layers['service'] == 0:
            for candidate in all_candidates:
                if self._is_service(candidate) and candidate not in selected:
                    selected.append(candidate)
                    break
        
        return selected
    
    def _is_controller(self, symbol: CodeSymbol) -> bool:
        """判断是否为 Controller"""
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.CONTROLLER_ANNOTATIONS:
            return True
        
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        return any(kw in path_lower or kw in name_lower for kw in self.CONTROLLER_KEYWORDS)
    
    def _is_service(self, symbol: CodeSymbol) -> bool:
        """判断是否为 Service"""
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.SERVICE_ANNOTATIONS:
            return True
        
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        return any(kw in path_lower or kw in name_lower for kw in self.SERVICE_KEYWORDS)
    
    def _is_repository(self, symbol: CodeSymbol) -> bool:
        """判断是否为 Repository"""
        annotations = {ann.name for ann in symbol.annotations}
        if annotations & self.REPOSITORY_ANNOTATIONS:
            return True
        
        path_lower = symbol.file_path.lower()
        name_lower = symbol.qualified_name.lower()
        return any(kw in path_lower or kw in name_lower for kw in self.REPOSITORY_KEYWORDS)
    
    def _build_context(
        self,
        symbols: list[CodeSymbol],
        requirement: Requirement
    ) -> str:
        """构造上下文字符串"""
        parts = []
        
        # 按层级分组
        controllers = [s for s in symbols if self._is_controller(s)]
        services = [s for s in symbols if self._is_service(s)]
        repositories = [s for s in symbols if self._is_repository(s)]
        
        # Controller 层
        if controllers:
            parts.append("# Controller 层（入口）")
            for symbol in controllers:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.annotations:
                    parts.append(f"注解: {', '.join([f'@{a.name}' for a in symbol.annotations])}")
                if symbol.doc:
                    parts.append(f"文档: {symbol.doc[:200]}...")
                parts.append(f"```java\n{symbol.source[:500]}...\n```")
        
        # Service 层
        if services:
            parts.append("\n# Service 层（业务逻辑）")
            for symbol in services:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.annotations:
                    parts.append(f"注解: {', '.join([f'@{a.name}' for a in symbol.annotations])}")
                if symbol.doc:
                    parts.append(f"文档: {symbol.doc[:200]}...")
                parts.append(f"```java\n{symbol.source[:500]}...\n```")
        
        # Repository 层
        if repositories:
            parts.append("\n# Repository 层（数据访问）")
            for symbol in repositories:
                parts.append(f"\n## {symbol.qualified_name}")
                if symbol.annotations:
                    parts.append(f"注解: {', '.join([f'@{a.name}' for a in symbol.annotations])}")
                parts.append(f"```java\n{symbol.source[:300]}...\n```")
        
        context = "\n".join(parts)
        
        # 控制长度
        if len(context) > self.max_context_chars:
            context = context[:self.max_context_chars] + "\n\n... (上下文已截断)"
        
        return context
    
    def _build_system_prompt(self) -> str:
        """构造 system prompt"""
        return """你是一位经验丰富的系统架构师和技术负责人。你的任务是基于现有的 Java 代码架构，为给定的需求设计技术实现方案。

你必须输出严格的 JSON 格式，包含以下字段：

- `scenario`: 固定为 "arch_design"
- `instruction`: 需求的简要描述（从 goal 提取）
- `context`: 相关代码上下文（直接使用提供的代码）
- `answer`: 详细的设计方案，必须包含以下章节：
  1. **现状画像**：当前架构的关键特征、技术栈、已有能力
  2. **方案概述**：整体设计思路、核心技术选型、架构变更
  3. **接口与数据变更**：新增/修改的接口、数据结构、配置项
  4. **迁移与回滚**：灰度策略、数据迁移方案、回滚预案
  5. **测试计划**：单元测试、集成测试、性能测试要点
  6. **风险与权衡**：技术风险、复杂度评估、可能的问题
- `thought`: 结构化的推理过程，包含：
  - `observations`: 从现有代码中观察到的事实（数组）
  - `inferences`: 基于观察的设计推断（数组）
  - `evidence_refs`: 证据引用（必须至少 2 个：Controller 入口 + Service 核心逻辑），每个包含：
    * `symbol_id`: 符号标识
    * `file_path`: 文件路径
    * `start_line`: 起始行号（整数）
    * `end_line`: 结束行号（整数）
    * `source_hash`: 源码哈希
  - `assumptions`: 设计假设或待验证的点（数组）
- `repo_commit`: 仓库提交哈希

**设计原则**：
1. 充分复用现有架构和代码
2. 最小化改动范围，降低风险
3. 考虑性能、可维护性、可扩展性
4. 提供清晰的实施路径

**重要约束**：
- 不要输出自由文本的长篇思考过程（CoT）
- 所有推理必须结构化为 observations/inferences/assumptions
- evidence_refs 必须包含完整字段：symbol_id, file_path, start_line, end_line, source_hash
- answer 必须严格按照 6 个章节组织"""
    
    def _build_user_prompt(
        self,
        requirement: Requirement,
        context: str,
        symbols: list[CodeSymbol],
        repo_commit: str
    ) -> str:
        """构造 user prompt"""
        # 选择关键符号用于示例
        controller_symbol = next((s for s in symbols if self._is_controller(s)), symbols[0])
        service_symbol = next((s for s in symbols if self._is_service(s)), symbols[0] if len(symbols) > 0 else None)
        
        prompt = f"""请基于现有架构，为以下需求设计技术实现方案。

# 需求详情

**需求ID**: {requirement.id}

**目标**: {requirement.goal}

**约束条件**:
{chr(10).join([f'- {c}' for c in requirement.constraints])}

**验收标准**:
{chr(10).join([f'- {a}' for a in requirement.acceptance_criteria])}

**非目标**:
{chr(10).join([f'- {n}' for n in requirement.non_goals])}

# 现有代码架构

{context}

# 输出要求

请生成 JSON 格式的设计方案，包含 scenario、instruction、context、answer、thought 和 repo_commit。

**示例 JSON 结构**：
```json
{{
  "scenario": "arch_design",
  "instruction": "{requirement.goal[:50]}...",
  "context": "// 现有代码上下文\\n...",
  "answer": "## 1. 现状画像\\n当前系统采用 Spring Boot + MyBatis 架构...\\n\\n## 2. 方案概述\\n引入 Redis 作为缓存层...\\n\\n## 3. 接口与数据变更\\n- 新增配置：redis.host...\\n\\n## 4. 迁移与回滚\\n采用灰度发布...\\n\\n## 5. 测试计划\\n- 单元测试...\\n\\n## 6. 风险与权衡\\n- 缓存一致性风险...",
  "thought": {{
    "observations": [
      "现有系统使用 {controller_symbol.qualified_name} 作为入口",
      "业务逻辑在 {service_symbol.qualified_name if service_symbol else 'Service'} 层处理",
      "..."
    ],
    "inferences": [
      "可以在 Service 层添加缓存切面",
      "需要引入 RedisTemplate 依赖",
      "..."
    ],
    "evidence_refs": [
      {{
        "symbol_id": "{controller_symbol.symbol_id}",
        "file_path": "{controller_symbol.file_path}",
        "start_line": {controller_symbol.start_line},
        "end_line": {controller_symbol.end_line},
        "source_hash": "{controller_symbol.source_hash}"
      }}"""
        
        if service_symbol:
            prompt += f""",
      {{
        "symbol_id": "{service_symbol.symbol_id}",
        "file_path": "{service_symbol.file_path}",
        "start_line": {service_symbol.start_line},
        "end_line": {service_symbol.end_line},
        "source_hash": "{service_symbol.source_hash}"
      }}"""
        
        prompt += f"""
    ],
    "assumptions": [
      "假设 Redis 已部署并可用",
      "假设团队熟悉 Spring Cache 注解"
    ]
  }},
  "repo_commit": "{repo_commit}"
}}
```

**注意**：context 字段应该包含相关代码片段的精简版本。

现在请输出完整的 JSON（不要包含 Markdown 标记）："""
        
        return prompt
    
    def _validate_sample(
        self,
        sample: TrainingSample,
        requirement: Requirement,
        repo_commit: str,
        symbols: list[CodeSymbol]
    ) -> tuple[bool, list[str]]:
        """校验训练样本"""
        errors = []
        
        # 创建符号索引
        symbol_index = {s.symbol_id: s for s in symbols}
        
        # 1. 检查 repo_commit
        if sample.repo_commit != repo_commit:
            errors.append(f"repo_commit mismatch: {sample.repo_commit} != {repo_commit}")
        
        # 2. 检查 scenario
        if sample.scenario != "arch_design":
            errors.append(f"scenario should be 'arch_design', got '{sample.scenario}'")
        
        # 3. 检查 thought 结构
        if not sample.thought:
            errors.append("thought is missing")
        else:
            if not sample.thought.observations:
                errors.append("thought.observations is empty")
            if not sample.thought.inferences:
                errors.append("thought.inferences is empty")
            if not sample.thought.evidence_refs or len(sample.thought.evidence_refs) < 2:
                errors.append("thought.evidence_refs must have at least 2 items")
        
        # 4. 检查 evidence_refs
        if sample.thought and sample.thought.evidence_refs:
            for ref in sample.thought.evidence_refs:
                if ref.symbol_id not in symbol_index:
                    errors.append(f"evidence_ref symbol_id not found: {ref.symbol_id}")
                else:
                    ref_symbol = symbol_index[ref.symbol_id]
                    if ref.source_hash != ref_symbol.source_hash:
                        errors.append(
                            f"evidence_ref source_hash mismatch for {ref.symbol_id}"
                        )
        
        # 5. 检查 answer 结构（是否包含必要章节）
        required_sections = ['现状画像', '方案概述', '接口与数据变更', '迁移与回滚', '测试计划', '风险与权衡']
        missing_sections = [s for s in required_sections if s not in sample.answer]
        
        if len(missing_sections) > 2:  # 允许缺少最多 2 个章节
            errors.append(f"answer missing critical sections: {missing_sections}")
        
        # 6. 检查长度
        if len(sample.instruction) < 10:
            errors.append("instruction too short (< 10 chars)")
        if len(sample.answer) < 100:
            errors.append("answer too short (< 100 chars)")
        
        return len(errors) == 0, errors
    
    def _save_samples(self, samples: list[TrainingSample]):
        """保存训练样本"""
        if not samples:
            logger.warning("No samples to save")
            return
        
        with open(self.raw_output_path, 'w', encoding='utf-8') as f:
            for sample in samples:
                f.write(sample.model_dump_json() + '\n')
        
        logger.info(f"Saved {len(samples)} samples to {self.raw_output_path}")
    
    def _log_rejected(self, requirement: Requirement, reason: str, raw_output: dict | None):
        """记录被拒绝的样本"""
        entry = {
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'requirement_id': requirement.id,
            'goal': requirement.goal,
            'reason': reason,
            'raw_output': raw_output
        }
        
        try:
            with open(self.rejected_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Failed to log rejected sample: {e}")
    
    def print_summary(self):
        """打印生成摘要"""
        print("\n" + "=" * 70)
        print(" 架构设计方案生成摘要")
        print("=" * 70)
        print(f"总需求数: {self.stats['total_requirements']}")
        print(f"成功生成: {self.stats['generated_samples']}")
        print(f"生成失败: {self.stats['rejected_samples']}")
        
        if self.stats['validation_errors']:
            print(f"\n校验错误类型分布:")
            error_types = Counter()
            for err_entry in self.stats['validation_errors']:
                for err in err_entry['errors']:
                    error_types[err.split(':')[0]] += 1
            
            for err_type, count in error_types.most_common():
                print(f"  - {err_type}: {count}")
        
        print(f"\n输出文件:")
        print(f"  - 需求文件: {self.requirements_path}")
        print(f"  - 成功样本: {self.raw_output_path}")
        print(f"  - 失败样本: {self.rejected_path}")
        print("=" * 70)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='场景 2：架构设计方案生成器')
    parser.add_argument(
        '--symbols',
        default='data/raw/extracted/symbols.jsonl',
        help='符号文件路径 (default: data/raw/extracted/symbols.jsonl)'
    )
    parser.add_argument(
        '--repo-commit',
        default=None,
        help='仓库 commit hash（可选，默认从符号文件推断）'
    )
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='最大生成样本数（可选，默认从配置读取）'
    )
    
    args = parser.parse_args()
    
    # 加载配置
    config = Config()
    
    # 覆盖配置
    if args.max_samples:
        config._config['design_generator'] = config._config.get('design_generator', {})
        config._config['design_generator']['max_samples'] = args.max_samples
    
    # 初始化生成器
    generator = DesignGenerator(config=config)
    
    # 生成
    try:
        samples = generator.generate_from_repo(
            symbols_path=args.symbols,
            repo_commit=args.repo_commit
        )
        
        # 打印摘要
        generator.print_summary()
        
        return 0 if samples else 1
        
    except Exception as e:
        logger.error(f"Design generation failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
