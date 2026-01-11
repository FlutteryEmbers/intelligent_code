# 质量清洗增强（关键词黑名单过滤）设计文档

遵循 `docs/ai_rules/ai_design_rules.md`：增量优先、配置复用、决策透明、仅做设计。

---

## 1. 现状审计（Audit）

### 1.1 现有逻辑分布

- **Secrets 过滤**：`src/pipeline/steps/secrets_scan.py` 支持 drop/sanitize。
- **长度约束**：`src/utils/data/validator.py` 通过 `quality.*` 产生 warning，可选 fail-on-warnings。
- **去重**：`src/pipeline/steps/deduplication.py` 使用 SimHash。

### 1.2 缺口与冗余

- **缺口**：缺少“关键词黑名单过滤”，例如“作为人工智能”等废话模板。
- **冗余风险**：若新增单独过滤 step，可能与 secrets_scan 重复扫描文本。

---

## 2. 目标架构（Target Architecture）

### 2.1 更新后的逻辑流向（增量）

```
... → Merge → Dedup → SecretsScan(+Blacklist) → Split → Export
```

- 在 **SecretsScanStep** 内加入“黑名单过滤”逻辑（不新增 pipeline step）。
- 黑名单命中后按安全策略处理：drop 或 sanitize（复用 `safety.mode`）。

### 2.2 模块职责

- **SecretsScanStep**：统一负责安全过滤 + 文本黑名单过滤。
- **配置层**：复用 `safety` 模块扩展黑名单字段。

---

## 3. 迁移映射（Migration Mapping）

不新增顶层模块，仅扩展 `safety`：

- 旧 Key → 新 Key
  - `safety.mode` → `safety.mode`（保留）
  - `safety.*` → `safety.blacklist_keywords`（新增字段）

映射策略：新增字段为可选，旧配置不变即可运行。

---

## 4. 阶段性路径（Phases）

### Phase 1（影子配置）

- 仅记录命中数量与样本 id（report-only）。
- 不改变输出样本集合。

### Phase 2（逻辑重定向）

- 开启 drop/sanitize 行为（与 `safety.mode` 一致）。
- 输出 `blacklist_dropped.jsonl` 或复用 `secrets_dropped.jsonl` 的附加字段。

### Phase 3（旧逻辑弃用）

- 若已有外部脚本做黑名单过滤，统一迁移到本逻辑。

---

## 5. 决策平衡（Trade-offs）

### 决策 1：复用 SecretsScan 还是新增 Step

| 复用 SecretsScan（推荐） | 变更最小、无需调整 pipeline 顺序 | 日志需区分 secrets vs blacklist |

### 决策 2：命中后处理方式（新增 keep）

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| drop | 质量更纯净 | 数据量下降 |
| keep（demo 推荐） | 不影响样本量，便于回溯 | 低质样本可能进入训练集 |
| sanitize | 保留样本 | 可能保留“废话结构” |

说明：三种处理方式都需要实现；默认选择（demo）：`keep`。

---

## 6. 配置建议（复用现有模块）

仅扩展 `safety`（不新增顶层模块）：

```yaml
safety:
  mode: "keep"            # drop | keep | sanitize
  blacklist_keywords:
    - "作为人工智能"
    - "无法访问"
    - "不具备"
    - "抱歉"
```

---

## 7. 验收标准

- 命中样本可统计与追踪（报告/日志）。
- 不影响 secrets 过滤的既有行为。
- 旧配置可无修改运行（字段可选）。

说明：
- **keep**：命中黑名单仅记录日志/报告，不做替换也不丢弃样本。
- **drop**：命中即丢弃样本。
- **sanitize**：命中后替换/脱敏再保留样本。
