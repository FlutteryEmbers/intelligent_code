# QA 生成器使用指南（场景 1）

## 概述

`QAGenerator` 实现了**场景 1：基于业务规则和流程的问答对生成**。

它从解析的 Java 代码符号中自动提取业务逻辑，生成结构化的问答训练数据，包含：

- ✅ **智能符号选择**：优先处理带业务注解的方法（@Transactional、@Service、REST 端点等）
- ✅ **上下文构造**：包含完整方法信息（注解、JavaDoc、源码），并智能控制长度
- ✅ **结构化推理**：生成包含 observations/inferences/evidence_refs 的推理过程
- ✅ **质量校验**：自动验证 repo_commit、evidence_refs、字段完整性等
- ✅ **失败回收**：记录所有失败样本到 rejected 文件，便于分析改进

---

## 快速开始

### 1. 确保已解析代码仓库

首先运行 Java 解析器：

```bash
python tests/test_java_parser.py
```

这会生成 `data/raw/extracted/symbols.jsonl`。

### 2. 运行测试

```bash
python tests/test_qa_generator.py
```

测试会生成 5 个样本用于验证。

### 3. 完整生成

```bash
python -m src.engine.qa_generator --max-samples 100
```

---

## 命令行使用

### 基本用法

```bash
python -m src.engine.qa_generator
```

### 指定符号文件

```bash
python -m src.engine.qa_generator --symbols data/raw/extracted/symbols.jsonl
```

### 限制生成数量

```bash
python -m src.engine.qa_generator --max-samples 50
```

### 调整批处理大小

```bash
python -m src.engine.qa_generator --batch-size 10
```

### 完整示例

```bash
python -m src.engine.qa_generator \
  --symbols data/raw/extracted/symbols.jsonl \
  --max-samples 100 \
  --batch-size 5 \
  --repo-commit abc123def
```

---

## 配置选项

### 通过配置文件

编辑 `configs/pipeline.yaml`：

```yaml
qa_generator:
  max_context_chars: 16000       # 单个上下文最大字符数
  batch_size: 5                  # 批处理大小
  max_samples: 50                # 最大生成样本数
  priority_annotations:          # 高优先级注解
    - "Transactional"
    - "GetMapping"
    - "PostMapping"
    - "Service"
```

### 通过代码

```python
from src.engine import QAGenerator
from src.utils import Config

config = Config()
config._config['qa_generator'] = {
    'max_context_chars': 20000,
    'batch_size': 10,
    'max_samples': 200
}

generator = QAGenerator(config=config)
samples = generator.generate_from_repo()
```

---

## 输出文件

### 1. qa_raw.jsonl

成功生成的训练样本（JSONL 格式）：

```json
{
  "question": "该方法如何保证用户创建操作的数据一致性？",
  "answer": "该方法通过以下机制保证一致性：\n1. 使用 @Transactional 注解确保原子性...",
  "thought": {
    "observations": [
      "方法标注了 @Transactional 注解",
      "方法中包含数据库写入操作",
      "存在异常处理逻辑"
    ],
    "inferences": [
      "该操作需要事务保证",
      "失败时会自动回滚",
      "遵循 ACID 原则"
    ],
    "evidence_refs": [
      {
        "symbol_id": "src/User.java:com.example.User.createUser:15",
        "source_hash": "abc123...",
        "line_range": "15-25",
        "excerpt": "@Transactional\npublic void createUser(..."
      }
    ],
    "assumptions": []
  },
  "scenario": "qa_rule",
  "repo_commit": "abc123def456",
  "quality": {
    "schema_ok": true,
    "evidence_ok": true,
    "source_symbol": "src/User.java:com.example.User.createUser:15"
  }
}
```

### 2. qa_rejected.jsonl

失败的样本记录：

```json
{
  "timestamp": "2026-01-03T12:00:00Z",
  "symbol_id": "src/Example.java:com.example.Example.method:10",
  "qualified_name": "com.example.Example.method",
  "reason": "Validation failed",
  "raw_output": {
    "errors": ["thought.evidence_refs is empty"],
    "sample": { ... }
  }
}
```

---

## 符号选择策略

### 优先级评分

QAGenerator 使用评分系统选择最有价值的方法：

| 特征 | 分数 |
|------|------|
| `@Transactional` | +10 |
| REST 映射（@GetMapping 等） | +8 |
| `@Scheduled` | +6 |
| `@Async` | +5 |
| 类名含 Service/Controller | +3 |
| 有 JavaDoc | +2 |
| 方法名含业务关键词 | +1 |

### 业务关键词

- create, update, delete, save
- process, handle, execute
- validate

### 示例

```java
@Service
public class UserService {
    
    // 高分：@Transactional(10) + 业务关键词(1) + JavaDoc(2) = 13
    /**
     * 创建新用户
     */
    @Transactional
    public void createUser(User user) {
        // ...
    }
    
    // 低分：无注解 = 0（不会被选择）
    private String formatName(String name) {
        return name.toUpperCase();
    }
}
```

---

## 上下文构造

### 包含内容

```
方法完全限定名: com.example.UserService.createUser
文件路径: src/main/java/com/example/UserService.java
位置: 第 15-35 行

注解:
  @Transactional(isolation = REPEATABLE_READ)
  @PreAuthorize("hasRole('ADMIN')")

JavaDoc:
/**
 * 创建新用户
 * @param user 用户对象
 * @throws DuplicateException 用户已存在时抛出
 */

方法源码:
```java
@Transactional(isolation = REPEATABLE_READ)
public void createUser(User user) throws DuplicateException {
    // 验证用户
    if (userRepository.existsByUsername(user.getUsername())) {
        throw new DuplicateException("用户名已存在");
    }
    
    // 保存用户
    userRepository.save(user);
    
    // 发送欢迎邮件
    emailService.sendWelcomeEmail(user);
}
```
```

### 长度控制

- **最大长度**：`max_context_chars`（默认 16000）
- **超出策略**：截断源码部分，保留注解和 JavaDoc
- **截断标记**：`// ... (源码已截断)`

---

## System Prompt 设计

生成器使用精心设计的 system prompt，强调：

1. **角色定位**：资深 Java 架构师和代码审查专家
2. **分析要点**：
   - 业务规则
   - 一致性保证
   - 错误处理
   - 架构模式

3. **输出约束**：
   - 严格 JSON 格式
   - 结构化推理（禁止自由 CoT）
   - 必须包含 evidence_refs
   - 不确定内容放到 assumptions

---

## 质量校验

### 自动校验项

1. **repo_commit 一致性**
   - 样本的 repo_commit 必须与符号文件一致

2. **scenario 正确性**
   - 必须为 `"qa_rule"`

3. **thought 完整性**
   - observations 非空
   - inferences 非空
   - evidence_refs 至少 1 个

4. **evidence_refs 有效性**
   - symbol_id 在符号索引中存在
   - source_hash 与实际符号匹配

5. **内容长度**
   - question ≥ 10 字符
   - answer ≥ 20 字符

### 校验失败处理

- 记录到 `qa_rejected.jsonl`
- 包含详细错误信息
- 保留原始 LLM 输出用于调试

---

## 使用示例

### 示例 1：基本用法

```python
from src.engine import QAGenerator

generator = QAGenerator()
samples = generator.generate_from_repo()

print(f"生成了 {len(samples)} 个样本")
```

### 示例 2：限制生成数量

```python
from src.engine import QAGenerator
from src.utils import Config

config = Config()
config._config['qa_generator'] = {'max_samples': 20}

generator = QAGenerator(config=config)
samples = generator.generate_from_repo()
```

### 示例 3：分析统计

```python
from src.engine import QAGenerator
from collections import Counter

generator = QAGenerator()
samples = generator.generate_from_repo()

# 统计问题类型
keywords = []
for sample in samples:
    if '一致性' in sample.question:
        keywords.append('一致性')
    if '事务' in sample.question:
        keywords.append('事务')
    if '错误处理' in sample.question:
        keywords.append('错误处理')

print("问题类型分布:", Counter(keywords))
```

### 示例 4：手动校验样本

```python
import json

with open('data/intermediate/qa_raw.jsonl', 'r') as f:
    for line in f:
        sample = json.loads(line)
        
        # 检查推理质量
        if sample['thought']:
            obs_count = len(sample['thought']['observations'])
            inf_count = len(sample['thought']['inferences'])
            ev_count = len(sample['thought']['evidence_refs'])
            
            print(f"样本质量: obs={obs_count}, inf={inf_count}, ev={ev_count}")
```

---

## 性能优化

### 1. 调整批处理大小

```yaml
qa_generator:
  batch_size: 10  # 增大批处理可提高吞吐量
```

### 2. 限制最大样本数

```yaml
qa_generator:
  max_samples: 50  # 避免成本过高
```

### 3. 减小上下文长度

```yaml
qa_generator:
  max_context_chars: 12000  # 减少 token 消耗
```

---

## 故障排查

### 问题 1：没有候选符号

**症状**：`Selected 0 candidates`

**原因**：代码仓库中没有带业务注解的方法

**解决**：
- 检查是否为 Spring 项目
- 调整 `BUSINESS_ANNOTATIONS` 列表
- 降低优先级阈值

### 问题 2：LLM 生成失败

**症状**：大量样本进入 `qa_rejected.jsonl`

**原因**：
- LLM 模型不合适（如 qwen2.5-coder）
- Prompt 不够清晰
- 上下文过长

**解决**：
- 使用 qwen2.5:7b 或更大模型
- 检查 Ollama 服务状态
- 减小 `max_context_chars`

### 问题 3：校验失败

**症状**：`Validation failed: evidence_refs is empty`

**原因**：LLM 未按要求生成 evidence_refs

**解决**：
- 增强 system prompt
- 在 user prompt 中提供示例
- 使用更大的模型

---

## 输出样本示例

### 完整样本

```json
{
  "question": "UserService.createUser 方法如何保证用户创建的原子性和一致性？",
  "answer": "该方法通过以下机制保证原子性和一致性：\n\n1. **事务管理**：\n   - 使用 @Transactional 注解，确保整个操作在单一事务中执行\n   - 任何步骤失败都会触发回滚，保证数据不会部分提交\n\n2. **唯一性检查**：\n   - 在保存前检查用户名是否已存在\n   - 抛出 DuplicateException 防止重复用户\n\n3. **风险点**：\n   - 并发场景下可能出现竞态条件\n   - 建议在数据库层面添加唯一索引约束\n   - 邮件发送失败会导致事务回滚，可考虑异步处理",
  "thought": {
    "observations": [
      "方法标注了 @Transactional 注解",
      "包含用户名唯一性检查逻辑",
      "依次执行：验证 -> 保存 -> 发送邮件",
      "使用 userRepository.save() 持久化数据"
    ],
    "inferences": [
      "该方法需要事务保证，任何步骤失败都会回滚",
      "唯一性检查防止重复用户创建",
      "邮件发送在事务内，失败会影响用户创建",
      "遵循 Spring 声明式事务管理模式"
    ],
    "evidence_refs": [
      {
        "symbol_id": "src/UserService.java:com.example.UserService.createUser:15",
        "source_hash": "abc123def456...",
        "line_range": "15-28",
        "excerpt": "@Transactional\npublic void createUser(User user) throws DuplicateException {\n    if (userRepository.existsByUsername(user.getUsername())) {\n        throw new DuplicateException(\"用户名已存在\");\n    }\n    userRepository.save(user);\n    emailService.sendWelcomeEmail(user);\n}"
      }
    ],
    "assumptions": [
      "假设 userRepository 使用 JPA/Hibernate 实现",
      "假设默认事务隔离级别为 READ_COMMITTED"
    ]
  },
  "scenario": "qa_rule",
  "repo_commit": "abc123def456789",
  "quality": {
    "schema_ok": true,
    "evidence_ok": true,
    "source_symbol": "src/UserService.java:com.example.UserService.createUser:15"
  }
}
```

---

## 与其他模块集成

### 与 JavaParser 集成

```python
from src.parser import JavaParser, get_repo_commit
from src.engine import QAGenerator

# 1. 解析代码
parser = JavaParser()
commit = get_repo_commit("/path/to/repo")
symbols = parser.parse_repo("/path/to/repo", commit)

# 2. 生成 QA
generator = QAGenerator()
samples = generator.generate_from_repo(
    symbols_path="data/raw/extracted/symbols.jsonl",
    repo_commit=commit
)
```

### 与质量检查器集成（未来）

```python
from src.engine import QAGenerator, QualityChecker

generator = QAGenerator()
samples = generator.generate_from_repo()

checker = QualityChecker()
filtered_samples = checker.filter_samples(samples)
```

---

## 相关文档

- [项目需求](project_requirement.md)
- [数据结构设计](SCHEMAS.md)
- [Java 解析器](JAVA_PARSER_GUIDE.md)
- [LLM 客户端](LLM_CLIENT.md)

---

**场景 1 的 QA 生成器已完成！** 🎉

下一步：实现场景 2 的架构设计方案生成器。
