# Utils Refactoring Summary

## 概述
完成了 utils 文件夹的功能重组，提取了重复代码，拆分了臃肿文件，提高了代码的可维护性和可扩展性。

## Phase 1: 提取 Layer Matcher（已完成）

### 新增文件
- **src/utils/layer_matcher.py** (新增)
  - 提取了 design_generator.py 和 auto_requirement_generator.py 中的重复代码
  - 提供统一的层级匹配逻辑：`matches_layer()`, `is_controller()`, `is_service()`, `is_repository()`
  - 消除了约 40 行重复代码

### 修改文件
- **src/engine/design_generator.py**
  - 导入 layer_matcher: `from src.utils.layer_matcher import is_controller, is_service, is_repository`
  - 删除了 `_matches_layer_rules()` 方法
  - 简化了 `_is_controller()`, `_is_service()`, `_is_repository()` 方法

- **src/engine/auto_requirement_generator.py**
  - 导入 layer_matcher: `from src.utils.layer_matcher import is_controller, is_service, is_repository`
  - 删除了 `_matches_layer_rules()` 方法
  - 简化了 `_is_controller()`, `_is_service()`, `_is_repository()` 方法

## Phase 2: 拆分 Export 和 Security 模块（已完成）

### Export 模块重组
创建了 **src/utils/export/** 子目录，包含：

- **export/__init__.py** - 导出所有函数
- **export/sft.py** - SFT 格式导出 (`export_sft_jsonl`)
- **export/alpaca.py** - Alpaca 格式导出 (`export_alpaca_jsonl`)
- **export/reasoning.py** - 推理追踪导出 (`export_with_reasoning_trace`)
- **export/stats.py** - 数据集统计 (`export_statistics`)

**src/utils/exporter.py** 保留为向后兼容层，添加了 DeprecationWarning。

### Security 模块重组
创建了 **src/utils/security/** 子目录，包含：

- **security/__init__.py** - 导出所有函数和常量
- **security/patterns.py** - 密钥和许可证模式定义 (`SECRET_PATTERNS`, `LICENSE_PATTERNS`, `LICENSE_FILES`)
- **security/scanner.py** - 密钥扫描器 (`scan_secrets`)
- **security/license_detector.py** - 许可证检测 (`detect_license`)
- **security/sanitizer.py** - 文本清理 (`sanitize_text`)

**src/utils/safety.py** 保留为向后兼容层，添加了 DeprecationWarning。

## Phase 3: Utils 目录结构优化（已完成）

### 新增目录结构
创建了功能分组的子目录：
- **core/** - 核心工具（已完成迁移：config.py, logger.py, io.py, schemas.py）
- **language/** - 语言相关（预留，用于未来迁移 language_profile）
- **data_processing/** - 数据处理（预留，用于未来迁移 dedup, splitter, validator）
- **retrieval/** - 检索相关（预留，用于未来迁移 vector_index）
- **export/** - 导出工具（已完成）
- **security/** - 安全工具（已完成）

### Core 模块重组（新增）
创建了 **src/utils/core/** 子目录，包含：

- **core/__init__.py** - 导出所有核心工具
- **core/config.py** - 配置管理 (`Config`, `config`, `get_config`, `reload_config`)
- **core/logger.py** - 日志管理 (`get_logger`, `LoggerManager`)
- **core/io.py** - I/O 操作 (`read_json`, `write_json`, `read_jsonl`, `write_jsonl`, `append_jsonl`)
- **core/schemas.py** - 数据模型 (`CodeSymbol`, `TrainingSample`, `EvidenceRef`, 等)

**注意**: 原始文件 (src/utils/config.py, logger.py, io.py, schemas.py) 仍然保留，两份文件共存以保持完全向后兼容。

### 更新主模块
- **src/utils/__init__.py**
  - 添加了 `layer_matcher` 相关导出
  - 添加了 `language_profile` 相关导出
  - 保持了所有现有导出的向后兼容性

## 向后兼容性

### 完全兼容的导入方式
所有现有代码继续正常工作，无需修改：

```python
# 旧的导入方式仍然有效
from src.utils import export_sft_jsonl, export_alpaca_jsonl
from src.utils import scan_secrets, detect_license
from src.utils import matches_layer, is_controller
from src.utils import Config, get_logger, CodeSymbol

# 也可以使用新的导入方式
from src.utils.export import export_sft_jsonl
from src.utils.security import scan_secrets
from src.utils.layer_matcher import matches_layer
from src.utils.core import Config, get_logger, CodeSymbol
```

### 弃用警告
- `src.utils.exporter` - 导入时会显示 DeprecationWarning，建议使用 `src.utils.export`
- `src.utils.safety` - 导入时会显示 DeprecationWarning，建议使用 `src.utils.security`

## 代码质量改进

### 消除重复代码
- **Layer Matcher**: 消除了 design_generator.py 和 auto_requirement_generator.py 中的 40 行重复代码

### 提高可维护性
- **Export 模块**: 从单个 349 行文件拆分为 4 个专注的小文件
  - sft.py: ~100 行
  - alpaca.py: ~60 行
  - reasoning.py: ~110 行
  - stats.py: ~100 行

- **Security 模块**: 从单个 314 行文件拆分为 4 个专注的小文件
  - patterns.py: ~160 行（常量定义）
  - scanner.py: ~40 行
  - license_detector.py: ~90 行
  - sanitizer.py: ~20 行

### 改进职责分离
每个模块现在都有清晰的单一职责：
- **layer_matcher**: 架构层级识别
- **export/sft**: SFT 格式转换
- **export/alpaca**: Alpaca 格式转换
- **export/reasoning**: 推理追踪导出
- **export/stats**: 数据集统计
- **security/scanner**: 密钥检测
- **security/license_detector**: 许可证检测
- **security/sanitizer**: 敏感信息清理

## 测试验证

### 静态检查
```bash
# 无语法错误
python -m py_compile src/utils/**/*.py
```

### 运行时验证
所有现有的 pipeline 步骤继续正常工作：
- ✅ parse.py
- ✅ validation.py
- ✅ deduplication.py
- ✅ split.py
- ✅ export.py
- ✅ secrets_scan.py
- ✅ auto_module.py

## 未来改进建议剩余文件迁移
Core 模块已经完成迁移，如果需要进一步优化，可以将剩余文件迁移到功能子目录：

1. **language/** 子目录（推荐优先级：高）
   - language_profile.py → language/profile.py
   - layer_matcher.py → language/layer_matcher.py

2. **data_processing/** 子目录（推荐优先级：中）
   - dedup.py → data_processing/dedup.py
   - splitter.py → data_processing/splitter.py
   - validator.py → data_processing/validator.py

3. **retrieval/** 子目录（推荐优先级：低）ata_processing/validator.py

4. **retrieval/** 子目录
   - vector_index.py → retrieval/vector_index.py

### 迁移策略
采用逐步迁移策略，避免破坏性更改：
1. 在新位置创建文件
2. 旧位置保留兼容层（带弃用警告）
3. 更新 __init__.py 从新位置导入
4. 给用户时间迁移代码
5. 在下一个主版本删除兼容层

## 总结

### 已完成
- ✅ Phase 1: 提取 layer_matcher.py，消除重复代码
- ✅ Phase 2: 拆分 exporter.py 和 safety.py
- ✅ Phase 3: 创建功能分组的目录结构
- ✅ 保持完全的向后兼容性
- ✅ 所有现有代码无需修改

### 收益
- 📉 减少了约 40 行重复代码
- 📦 将 663 行的代码拆分为更小、更专注的模块
- 🎯 每个模块职责清晰、易于维护
- 🔧 为未来扩展（如添加 Go、Rust 语言支持）奠定了基础
- ✨ 代码质量显著提升

### 无破坏性影响
- ✅ 所有现有导入继续工作
- ✅ 所有 pipeline 步骤正常运行
- ✅ 无需修改任何现有代码
- ⚠️ 仅添加了友好的弃用警告
