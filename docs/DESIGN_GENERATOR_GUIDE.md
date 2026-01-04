# 架构设计生成器使用指南（场景 2）

## 概述

`DesignGenerator` 实现了**场景 2：基于需求的架构设计方案生成**。

它结合轻量级 RAG 检索和 LLM 生成，为结构化需求自动生成详细的技术实现方案，包含：

- ✅ **结构化需求管理**：内置 5 个典型需求（缓存、幂等、读写分离、限流、异步）
- ✅ **两段式 RAG**：过滤（Controller/Service/Repository）+ 关键词检索
- ✅ **分层上下文**：自动识别并拼装 Controller、Service、Repository 层代码
- ✅ **结构化设计方案**：6 个必须章节（现状画像、方案概述、接口变更、迁移回滚、测试计划、风险权衡）
- ✅ **多证据引用**：至少 2 个证据（Controller 入口 + Service 核心逻辑）
- ✅ **质量校验**：验证 scenario、evidence_refs、answer 结构完整性

---

## 快速开始

### 1. 确保已解析代码仓库

```bash
python tests/test_java_parser.py
```

### 2. 运行测试

```bash
python tests/test_design_generator.py
```

测试会生成 2 个设计方案样本。

### 3. 完整生成

```bash
python -m src.engine.design_generator --max-samples 5
```

---

## 内置需求

### REQ-001: Redis 缓存层
- **目标**：为用户登录接口添加 Redis 缓存，提升高并发性能
- **约束**：30 分钟有效期，保证一致性，支持预热和失效
- **验收**：QPS 提升 5 倍，命中率 > 90%

### REQ-002: 订单幂等性
- **目标**：防止重复下单，实现幂等性保证
- **约束**：唯一流水号，持久化，明确错误，支持清理
- **验收**：相同请求返回相同结果，响应 < 10ms

### REQ-003: 读写分离
- **目标**：产品查询接口读写分离，提升查询性能
- **约束**：主库写从库读，处理延迟，自动切换
- **验收**：95% 读走从库，延迟 < 1 秒

### REQ-004: 限流保护
- **目标**：商品搜索接口限流，防止恶意刷单
- **约束**：用户 ID + IP 双重限流，令牌桶算法
- **验收**：单用户 10 QPS，单 IP 100 QPS

### REQ-005: 异步处理
- **目标**：用户收藏夹异步处理，优化响应时间
- **约束**：消息队列，立即返回，最终一致性，失败重试
- **验收**：响应 < 100ms，成功率 > 99.9%

---

## 命令行使用

### 基本用法

```bash
python -m src.engine.design_generator
```

### 指定符号文件

```bash
python -m src.engine.design_generator --symbols data/raw/extracted/symbols.jsonl
```

### 限制生成数量

```bash
python -m src.engine.design_generator --max-samples 3
```

### 完整示例

```bash
python -m src.engine.design_generator \
  --symbols data/raw/extracted/symbols.jsonl \
  --max-samples 5 \
  --repo-commit abc123def
```

---

## 配置选项

### 通过配置文件

编辑 `configs/pipeline.yaml`：

```yaml
design_generator:
  top_k_context: 6                 # RAG 检索返回的 top-k 数量
  max_context_chars: 20000         # 单个上下文最大字符数
  max_samples: 10                  # 最大生成样本数
  require_min_evidence: 2          # 最少证据引用数量
```

### 通过代码

```python
from src.engine import DesignGenerator
from src.utils import Config

config = Config()
config._config['design_generator'] = {
    'top_k_context': 8,
    'max_context_chars': 25000,
    'max_samples': 20
}

generator = DesignGenerator(config=config)
samples = generator.generate_from_repo()
```

---

## 输出文件

### 1. requirements.jsonl

结构化需求列表：

```json
{
  "id": "REQ-001",
  "goal": "为用户登录接口添加 Redis 缓存层，提升高并发场景下的性能",
  "constraints": [
    "使用 Redis 作为缓存存储",
    "缓存有效期为 30 分钟",
    "需要保证缓存与数据库数据一致性"
  ],
  "acceptance_criteria": [
    "登录 QPS 提升 5 倍以上",
    "缓存命中率 > 90%"
  ],
  "non_goals": [
    "不改变现有登录业务逻辑"
  ]
}
```

### 2. design_raw.jsonl

成功生成的设计方案：

```json
{
  "scenario": "arch_design",
  "instruction": "为用户登录接口添加 Redis 缓存层，提升高并发场景下的性能",
  "context": "# Controller 层（入口）\n## UserController.login\n...",
  "answer": "## 1. 现状画像\n当前系统采用 Spring Boot + MyBatis 架构...\n\n## 2. 方案概述\n引入 Spring Cache + Redis 作为缓存层...",
  "thought": {
    "observations": [
      "现有系统使用 UserController.login 作为登录入口",
      "业务逻辑在 UserService.authenticate 中处理",
      "使用 MyBatis 查询用户表"
    ],
    "inferences": [
      "可以在 Service 层添加 @Cacheable 注解",
      "需要引入 spring-boot-starter-data-redis 依赖",
      "缓存 key 使用用户名作为标识"
    ],
    "evidence_refs": [
      {
        "symbol_id": "UserController.java:com.example.UserController.login:20",
        "file_path": "src/main/java/com/example/UserController.java",
        "start_line": 20,
        "end_line": 35,
        "source_hash": "abc123..."
      },
      {
        "symbol_id": "UserService.java:com.example.UserService.authenticate:50",
        "file_path": "src/main/java/com/example/UserService.java",
        "start_line": 50,
        "end_line": 80,
        "source_hash": "def456..."
      }
    ],
    "assumptions": [
      "假设 Redis 已部署并可用",
      "假设团队熟悉 Spring Cache 注解"
    ]
  },
  "repo_commit": "abc123def456",
  "quality": {
    "schema_ok": true,
    "evidence_ok": true,
    "requirement_id": "REQ-001",
    "context_symbols": 6
  }
}
```

### 3. design_rejected.jsonl

失败的样本记录：

```json
{
  "timestamp": "2026-01-03T12:00:00Z",
  "requirement_id": "REQ-001",
  "goal": "为用户登录接口添加 Redis 缓存层...",
  "reason": "Validation failed",
  "raw_output": {
    "errors": ["thought.evidence_refs must have at least 2 items"],
    "sample": { ... }
  }
}
```

---

## RAG 检索策略

### 第一阶段：过滤候选

**基于注解**：
- Controller: `@RestController`, `@Controller`
- Service: `@Service`, `@Component`
- Repository: `@Repository`

**基于命名**：
- Controller: `controller`, `endpoint`, `api`, `rest`
- Service: `service`, `manager`, `handler`
- Repository: `repository`, `dao`, `mapper`
- Entity: `entity`, `model`, `dto`, `vo`

**示例**：
```java
// ✓ 会被选中
@RestController
public class UserController { ... }

@Service
public class UserService { ... }

// ✓ 会被选中（通过命名）
public class ProductServiceImpl { ... }
```

### 第二阶段：关键词检索

**评分规则**：
1. 关键词匹配（在 qualified_name/doc/source 中）：+1 分/词
2. Controller 注解：+3 分
3. Service 注解：+2 分
4. 有 JavaDoc：+1 分

**示例**：

需求："为用户登录接口添加 Redis 缓存"

关键词：`["用户", "登录", "缓存", "redis"]`

```java
// 高分：UserController.login
@RestController  // +3
public class UserController {
    /**
     * 用户登录  // +1 (JavaDoc) + 2 (关键词匹配)
     */
    @PostMapping("/login")  // +1 (关键词匹配)
    public Result login(...) { ... }
}
// 总分: 3 + 1 + 3 = 7 分
```

### 第三阶段：层级平衡

确保至少包含：
- 1 个 Controller（入口）
- 1 个 Service（核心逻辑）

**自动补充逻辑**：
```python
if 缺少 Controller:
    从候选中补充第一个 Controller
if 缺少 Service:
    从候选中补充第一个 Service
```

---

## 上下文拼装

### 分层结构

```markdown
# Controller 层（入口）

## UserController.login
注解: @RestController, @PostMapping
文档: 用户登录接口...
```java
@PostMapping("/login")
public Result login(@RequestBody LoginRequest request) {
    return userService.authenticate(request);
}
```

# Service 层（业务逻辑）

## UserService.authenticate
注解: @Service, @Transactional
文档: 认证用户身份...
```java
@Transactional
public User authenticate(LoginRequest request) {
    User user = userRepository.findByUsername(request.getUsername());
    // 验证密码...
    return user;
}
```

# Repository 层（数据访问）

## UserRepository.findByUsername
注解: @Repository
```java
User findByUsername(String username);
```
```

### 长度控制

- **最大长度**：`max_context_chars`（默认 20000）
- **超出策略**：截断后添加标记 `... (上下文已截断)`

---

## 设计方案结构

### 必须包含的 6 个章节

#### 1. 现状画像
- 当前架构的关键特征
- 使用的技术栈
- 已有的能力和限制

#### 2. 方案概述
- 整体设计思路
- 核心技术选型
- 主要架构变更

#### 3. 接口与数据变更
- 新增/修改的 API 接口
- 数据结构变更
- 配置项和依赖

#### 4. 迁移与回滚
- 灰度发布策略
- 数据迁移方案
- 回滚预案

#### 5. 测试计划
- 单元测试要点
- 集成测试场景
- 性能测试指标

#### 6. 风险与权衡
- 技术风险评估
- 复杂度分析
- 可能的问题和应对

---

## 使用示例

### 示例 1：基本用法

```python
from src.engine import DesignGenerator

generator = DesignGenerator()
samples = generator.generate_from_repo()

print(f"生成了 {len(samples)} 个设计方案")
```

### 示例 2：自定义需求

```python
from src.engine.design_generator import DesignGenerator, Requirement

custom_req = Requirement(
    id="REQ-CUSTOM",
    goal="为商品搜索接口添加 Elasticsearch 全文检索",
    constraints=[
        "使用 Elasticsearch 7.x",
        "保持 MySQL 和 ES 数据同步",
        "查询响应时间 < 100ms"
    ],
    acceptance_criteria=[
        "支持模糊搜索",
        "支持分词和高亮",
        "QPS > 1000"
    ],
    non_goals=["不支持复杂的聚合查询"]
)

generator = DesignGenerator()
samples = generator.generate_from_repo(requirements=[custom_req])
```

### 示例 3：分析上下文检索

```python
from src.engine import DesignGenerator
from src.engine.design_generator import BUILT_IN_REQUIREMENTS

generator = DesignGenerator()

# 加载符号
symbols = generator._load_symbols('data/raw/extracted/symbols.jsonl')

# 测试 RAG 检索
req = BUILT_IN_REQUIREMENTS[0]
relevant = generator._retrieve_context(req, symbols)

print(f"需求: {req.goal}")
print(f"检索到 {len(relevant)} 个相关符号:")
for symbol in relevant:
    print(f"  - {symbol.qualified_name}")
    print(f"    层级: {'Controller' if generator._is_controller(symbol) else 'Service' if generator._is_service(symbol) else 'Other'}")
```

### 示例 4：导出为 DataFrame

```python
import pandas as pd
import json

# 读取 design_raw.jsonl
samples = []
with open('data/intermediate/design_raw.jsonl', 'r') as f:
    for line in f:
        samples.append(json.loads(line))

# 转换为 DataFrame
df = pd.DataFrame([{
    'requirement_id': s['quality']['requirement_id'],
    'instruction': s['instruction'][:50],
    'evidence_count': len(s['thought']['evidence_refs']),
    'answer_length': len(s['answer'])
} for s in samples])

print(df)
```

---

## 质量校验

### 自动校验项

1. **scenario 正确性**：必须为 `"arch_design"`
2. **repo_commit 一致性**：与符号文件一致
3. **thought 完整性**：
   - observations 非空
   - inferences 非空
   - evidence_refs ≥ 2 个
4. **evidence_refs 有效性**：
   - symbol_id 存在于符号索引
   - source_hash 匹配
5. **answer 结构**：至少包含 4/6 个必须章节
6. **内容长度**：
   - instruction ≥ 10 字符
   - answer ≥ 100 字符

### 校验失败处理

- 记录到 `design_rejected.jsonl`
- 包含详细错误信息
- 保留原始 LLM 输出

---

## 性能优化

### 1. 调整 Top-K

```yaml
design_generator:
  top_k_context: 8  # 增大可提供更多上下文
```

### 2. 限制样本数

```yaml
design_generator:
  max_samples: 5  # 减少生成数量
```

### 3. 减小上下文长度

```yaml
design_generator:
  max_context_chars: 15000  # 减少 token 消耗
```

---

## 故障排查

### 问题 1：No relevant symbols found

**症状**：所有需求都找不到相关上下文

**原因**：代码仓库中没有明显的 Controller/Service/Repository 结构

**解决**：
- 检查是否为 Spring 项目
- 调整过滤关键词
- 放宽候选过滤条件

### 问题 2：LLM 生成失败

**症状**：大量样本进入 `design_rejected.jsonl`

**原因**：
- 上下文过长
- Prompt 不够清晰
- 模型不合适

**解决**：
- 减小 `max_context_chars`
- 使用更大的模型（qwen2.5:14b）
- 检查 Ollama 服务状态

### 问题 3：answer 缺少章节

**症状**：`answer missing critical sections`

**原因**：LLM 未按要求生成完整章节

**解决**：
- 增强 system prompt 的章节要求
- 在 user prompt 中提供示例
- 使用更大的模型

---

## 相关文档

- [项目需求](project_requirement.md)
- [数据结构设计](SCHEMAS.md)
- [Java 解析器](JAVA_PARSER_GUIDE.md)
- [QA 生成器](QA_GENERATOR_GUIDE.md)
- [LLM 客户端](LLM_CLIENT.md)

---

**场景 2 的架构设计生成器已完成！** 🎉

两个场景的数据生成器现已全部实现，可以开始生成完整的训练数据集。
