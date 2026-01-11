from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.core.base_generator import BaseGenerator
from src.utils.core.config import Config


class _PromptLoader(BaseGenerator):
    def __init__(self, config: Config):
        # Skip BaseGenerator init to avoid LLMClient creation.
        self.scenario = "qa_rule"
        self.config = config


def _build_prompt(loader: _PromptLoader, template_path: str) -> str:
    template_name = loader._resolve_template_name(template_path)
    assert template_name, f"Template not found for path: {template_path}"
    available_evidence = [
        {
            "symbol_id": "demo/Sample.java:Sample:1",
            "file_path": "demo/Sample.java",
            "start_line": 1,
            "end_line": 2,
            "source_hash": "SENTINEL_HASH",
        }
    ]
    return loader._build_composed_user_prompt(
        template_name,
        method_profile=json.dumps({"summary": "demo"}, ensure_ascii=False),
        source_code="class Sample {}",
        questions_per_method=1,
        symbol_id=available_evidence[0]["symbol_id"],
        file_path=available_evidence[0]["file_path"],
        start_line=available_evidence[0]["start_line"],
        end_line=available_evidence[0]["end_line"],
        source_hash=available_evidence[0]["source_hash"],
        repo_commit="DEMO_COMMIT",
        coverage_bucket="high",
        coverage_intent="how_to",
        question_type="how_to",
        scenario_constraints="无",
        constraint_strength="strong",
        constraint_rules="无",
        available_evidence_refs=json.dumps(available_evidence, ensure_ascii=False, indent=2),
    )


def test_prompt_loading_includes_evidence_refs() -> None:
    config = Config()
    config.reload(REPO_ROOT / "configs" / "launch.yaml")
    loader = _PromptLoader(config)
    prompt_paths = [
        config.get("question_answer.prompts.question_generation"),
        config.get("question_answer.prompts.coverage_generation"),
    ]

    for template_path in prompt_paths:
        assert template_path, "Prompt path is missing in launch.yaml"
        prompt = _build_prompt(loader, template_path)
        assert "SENTINEL_HASH" in prompt
        assert '"source_hash"' in prompt
        assert '"symbol_id"' in prompt
