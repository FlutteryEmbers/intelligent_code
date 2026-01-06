# Pipeline Steps Design Docs

本文档集合用于解释 `src/pipeline/orchestrator.py` 及 `src/pipeline/steps/*` 的设计与实现边界，作为后续 Design Doc 的可复用章节来源。内容以**当前实现**为准（文件工件驱动的离线管道），并在 Trade-offs 中记录已知限制与演进方向。

## 阅读顺序（建议）

1. `docs/pipeline/00-orchestrator-and-step-api.md`
2. `docs/pipeline/01-parse-step.md`
3. `docs/pipeline/02-auto-module-step.md`（可选分支：Auto QA / Profiles for Requirements）
4. `docs/pipeline/03-qa-generation-step.md`（标准 QA，Auto 开启时默认跳过）
5. `docs/pipeline/04-design-generation-step.md`
6. `docs/pipeline/05-validation-step.md`
7. `docs/pipeline/06-merge-step.md`
8. `docs/pipeline/07-deduplication-step.md`
9. `docs/pipeline/08-secrets-scan-step.md`
10. `docs/pipeline/09-split-step.md`
11. `docs/pipeline/10-export-step.md`

## 术语与约定

- **Request**：命令行入口 `main.py` 解析出的 `args`（离线 pipeline 的“请求”）。
- **DB / Storage**：当前实现中等价为文件系统上的 JSON/JSONL 工件（`data/raw` / `data/intermediate` / `data/final`）。
- **Artifact（工件）**：step 间共享的文件（例如 `symbols.jsonl`、`qa_raw.jsonl`、`all_dedup.jsonl`）。
- **Contract（契约）**：后续 step 对前置 artifact 的字段/路径/存在性假设（最关键的是 `TrainingSample` schema 与 `thought.evidence_refs`）。

## Related Docs

- `docs/SCHEMAS.md`：本项目所有核心 Pydantic schema 的设计说明与字段注解（理解 evidence_refs、split、validation 的基础）。
