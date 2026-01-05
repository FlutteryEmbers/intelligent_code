# Auto Requirement Generator - 使用指南

## 概述

RequirementGenerator 模块自动从代码仓库中生成架构改进需求，用于 DesignGenerator 生成设计方案训练样本。

## 配置

### 1. 启用自动需求生成

编辑 `configs/pipeline.yaml`:

```yaml
# 启用自动需求生成
auto_requirements:
  enabled: true                     # 启用自动生成
  max_requirements: 10              # 最多生成 10 个需求
  top_k_symbols: 12                 # 使用 Top-K 符号作为上下文
  require_min_evidence: 2           # 每个需求至少 2 个证据引用
  
# 让 DesignGenerator 使用自动生成的需求
design_generator:
  use_auto_requirements: true       # 使用自动生成的需求而非内置需求
```

### 2. 默认行为（不影响现有流程）

如果不修改配置，保持默认值：
- `auto_requirements.enabled: false`
- `design_generator.use_auto_requirements: false`

则行为与之前完全一致，使用 `configs/requirements.yaml` 中的内置需求。

## 使用方式

### 方式 1: 通过 main.py 运行（推荐）

```bash
# 运行完整 pipeline（包含自动需求生成）
python main.py

# 输出文件：
# - data/intermediate/requirements_auto.jsonl        # 生成的需求
# - data/intermediate/requirements_auto_rejected.jsonl  # 被拒绝的需求
# - data/intermediate/design_raw.jsonl              # 基于自动需求的设计方案
```

### 方式 2: 独立运行 RequirementGenerator

```bash
# 使用默认配置
python -m src.engine.auto_requirement_generator

# 指定符号文件和输出路径
python -m src.engine.auto_requirement_generator \
    --symbols data/raw/extracted/symbols.jsonl \
    --out data/intermediate/my_requirements.jsonl \
    --repo-commit abc123
```

## 生成的需求格式

每个需求包含以下字段（JSONL 格式，每行一个需求）：

```json
{
  "id": "REQ-AUTO-001",
  "goal": "为用户登录接口添加 Redis 缓存层，提升高并发场景下的性能",
  "constraints": [
    "使用 Redis 作为缓存存储",
    "缓存有效期为 30 分钟",
    "需要保证缓存与数据库数据一致性"
  ],
  "acceptance_criteria": [
    "登录 QPS 提升 5 倍以上",
    "缓存命中率 > 90%",
    "缓存穿透/雪崩有防护机制"
  ],
  "non_goals": [
    "不改变现有登录业务逻辑",
    "不引入分布式锁（MVP 阶段）"
  ],
  "evidence_refs": [
    {
      "symbol_id": "com.example.controller.UserController.login",
      "file_path": "src/main/java/com/example/controller/UserController.java",
      "start_line": 45,
      "end_line": 67,
      "source_hash": "sha256:abc123..."
    },
    {
      "symbol_id": "com.example.service.UserService.authenticate",
      "file_path": "src/main/java/com/example/service/UserService.java",
      "start_line": 89,
      "end_line": 112,
      "source_hash": "sha256:def456..."
    }
  ]
}
```

## 验证机制

RequirementGenerator 对生成的需求进行严格校验：

1. **字段完整性**: 所有必填字段存在
2. **可验证性**: `acceptance_criteria` 包含量化指标（QPS、ms、百分比等）
3. **证据有效性**: 
   - `evidence_refs` 数量 >= `require_min_evidence`
   - 所有 `symbol_id` 必须在 symbols.jsonl 中存在
   - `source_hash` 必须与符号文件中的值匹配
4. **内容质量**: goal 长度合理，基于实际代码上下文

未通过验证的需求会被写入 `requirements_auto_rejected.jsonl`。

## 需求类型

自动生成的需求涵盖常见架构改进场景：

- 缓存优化（Redis/本地缓存）
- 幂等性保证
- 限流保护
- 异步处理（消息队列）
- 读写分离
- 审计日志
- 错误码规范化
- 认证/鉴权增强
- 监控告警
- 数据校验

## 故障排查

### 问题 1: 生成的需求数量为 0

**可能原因**:
- symbols.jsonl 中没有足够的 Controller/Service/Repository 方法
- LLM 输出格式不符合预期
- 所有需求都未通过验证

**解决方法**:
1. 检查 `requirements_auto_rejected.jsonl` 查看拒绝原因
2. 调整 `max_requirements` 和 `top_k_symbols` 参数
3. 确认 Ollama 服务正常运行

### 问题 2: evidence_refs 验证失败

**可能原因**:
- LLM 未严格使用提供的 evidence_pool 中的值
- symbol_id 或 source_hash 不匹配

**解决方法**:
1. 检查 prompt 模板是否强调"必须使用精确值"
2. 降低 LLM temperature（增加确定性）
3. 增加 `top_k_symbols` 提供更多候选

### 问题 3: acceptance_criteria 不可验证

**可能原因**:
- 生成的验收标准过于空泛

**解决方法**:
1. 在 prompt 中强调"必须包含量化指标"
2. 检查 `VERIFIABLE_KEYWORDS` 是否需要扩充
3. 手动编辑 `configs/requirements.yaml` 提供高质量示例

## 最佳实践

1. **逐步启用**: 先生成少量需求（`max_requirements: 3`）验证质量，再增加
2. **定期检查**: 查看 rejected 文件了解常见失败模式
3. **混合使用**: 可同时使用自动生成 + 手动编写的需求（修改代码合并两者）
4. **迭代优化**: 根据生成质量调整 prompt 模板和配置参数

## 技术细节

- **符号过滤**: 复用 `DesignGenerator` 的层级识别逻辑（注解 + 关键词）
- **层级平衡**: 确保 Controller/Service/Repository 都有代表
- **随机种子**: 使用配置的 `seed` 保证可复现性
- **上下文控制**: 自动截断超长上下文（`max_context_chars`）
- **并发安全**: 单次运行，无并发问题

## 与现有流程的兼容性

✅ **完全向后兼容**:
- 默认配置下不影响任何现有行为
- 只有显式开启开关才执行自动生成
- 可与手动需求共存（通过代码扩展）

✅ **无破坏性修改**:
- 不修改现有类的核心逻辑
- 仅添加新模块和可选配置
- 输出路径独立（`requirements_auto.jsonl`）
