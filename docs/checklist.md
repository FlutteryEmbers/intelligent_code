# Dataset Rubric Checklist

状态说明：满足 / 部分满足 / 未满足

## 1. 目标对齐（Alignment）
- 用户提问形态覆盖（模糊问/指代问/多轮追问）：部分满足。证据：`configs/user_inputs/user_questions.yaml` 支持用户自定义问题，`src/engine/auto_question_generator.py` 自动生成问题，但没有约束多轮或指代问题。
- 回答预期（证据/结论/边界/可执行方案）：部分满足。证据：QA 输出结构由 `configs/prompts/auto_answer_generation.txt` 约束，设计方案结构由 `configs/prompts/design_user_prompt.txt` 约束；但校验未强制检查边界/假设是否显式出现（`src/engine/design_generator.py` 仅检查章节存在）。

## 2. 可验证正确（Verifiable Correctness）
- QA 证据可追溯：满足。证据：`src/utils/schemas.py` 的 `EvidenceRef` 和 `TrainingSample` 定义包含 `file_path/start_line/end_line/source_hash/repo_commit`，`src/utils/validator.py` 校验 evidence_refs 与 symbols_map 一致。
- Design 与现有模块/约束一致：部分满足。证据：`src/engine/design_generator.py` 依据 symbols 构造上下文并校验 evidence_refs 数量与章节，但 `src/pipeline/steps/validation.py` 为 report-only，不阻断后续合并/导出。

## 3. 覆盖充分且分布合理（Coverage & Distribution）
- 80/15/5 分布与覆盖策略：未满足。证据：当前仅有 `question_answer.questions_per_method` 与 `question_answer.max_questions`（`configs/launch.yaml`），没有按类型/难度/价值分层采样逻辑。
- 反例/负例与证据不足拒答：未满足。证据：问题生成器与设计生成器未提供“拒答/补充信息”样本策略（`src/engine/auto_question_generator.py`、`src/engine/auto_design_question_generator.py`）。

## 4. 高信噪比（High Signal-to-Noise）
- 结构稳定：部分满足。证据：`TrainingSample` schema 统一结构（`src/utils/schemas.py`），输出模板固定（`configs/prompts/*`）；但 JSON 格式错误仍会导致 rejected，且未强制重试或修复。
- 重复样本控制：部分满足。证据：`src/pipeline/steps/deduplication.py` 使用 SimHash 去重；但 validation 不是 gating，低质样本仍可能进入 `all_raw.jsonl`。
- 最小充分上下文：部分满足。证据：`configs/launch.yaml` 中 `core.max_context_chars`、`core.retrieval_top_k` 限制上下文长度，`src/engine/design_generator.py` 构造分层上下文并截断；但没有最小必要片段的自动裁剪策略。

## 5. 单条样本硬指标
- repo/commit/file_path/line_range/代码片段：满足。证据：`TrainingSample` 与 `EvidenceRef` 字段定义（`src/utils/schemas.py`）+ QA/Design 生成时填充 context 与 evidence_refs（`src/engine/answer_generator.py`、`src/engine/design_generator.py`）。
- 业务规则/非目标/边界清晰：部分满足。证据：`DesignQuestion` 支持 `non_goals`（`src/engine/design_generator.py`），但校验只检查章节存在，不保证回答中明确写出边界/非目标。

## 6. 推理 trace 质量
- Evidence-anchored steps / decision log：部分满足。证据：`ReasoningTrace` 结构化字段提供 evidence_refs（`src/utils/schemas.py`），但未要求逐步锚定证据或设计决策日志格式。
- 避免“内心独白式”推理：部分满足。证据：trace 为结构化字段，但 `src/utils/validator.py` 未校验 trace 内容质量，只校验证据一致性。

## 需要改进的事项（按重要性）
1. 增加“验证后 clean 工件”并让 Merge 以 clean 优先，避免 report-only 导致低质样本进入最终训练集（涉及 `src/pipeline/steps/validation.py` 与 `src/pipeline/steps/merge.py`）。
2. 引入覆盖与分布策略（按问题类型/难度/价值分层采样），并在配置中显式可控（涉及 `src/engine/auto_question_generator.py`、`configs/launch.yaml`）。
3. 增加反例/证据不足样本，训练“拒答或请求补充信息”的行为（涉及 QA/Design prompt 与生成逻辑）。
4. 约束 trace 质量：要求 Evidence-anchored steps 或设计决策日志格式，并在校验中检查（涉及 `src/utils/validator.py` 与 prompt 模板）。
5. 改进上下文最小充分集策略（基于依赖/调用链裁剪），减少上下文冗余与噪声（涉及 `src/engine/answer_generator.py` 与 `src/engine/design_generator.py`）。
