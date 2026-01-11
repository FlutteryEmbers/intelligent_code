# TODO: Coverage 硬编码收敛改进

- 日期: 2026-01-11
- 目标: 收敛覆盖率相关的业务口径硬编码，保留稳定算法兜底

## 背景
目前覆盖率推断与分布统计中仍存在硬编码（如 intent 关键词、bucket 默认目标、fallback 规则）。这些规则属于业务口径，后续可能调整，建议逐步配置化。

## 改进范围
- 业务口径配置化（建议）
  - intent 关键词
  - bucket 默认目标
  - fallback chain
  - label 文案与顺序
- 稳定算法兜底保留（保留硬编码）
  - unknown 回退逻辑
  - 基础推断逻辑结构

## 任务清单
1. 新增 `configs/types/coverage_rules.yaml`
   - intent_keywords
   - hard_keywords
   - bucket_targets
   - fallback_chain
2. `src/utils/data/coverage.py`
   - 替换 `INTENT_KEYWORDS` / `HARD_KEYWORDS` / `DEFAULT_TARGETS` / `FALLBACK_CHAIN` 为配置加载
   - 保留 unknown fallback 逻辑
3. `src/utils/generation/config_helpers.py`
   - 允许从类型配置覆盖默认 targets
4. 文档同步
   - `docs/features/03_quality/*` 增加“覆盖率规则配置来源”说明

## 验收标准
- 覆盖率推断结果不劣化（对现有测试无破坏）
- 业务口径调整无需改代码，只改配置文件
- unknown 仍然只作为兜底使用

## 风险提示
- 规则配置过度灵活可能引入不一致，需要设置默认值与校验
- 配置文件缺失/字段错误需要明确报错或回退
