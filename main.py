"""
Main entry point for intelligent training data generation pipeline.

This file has been refactored to use a modular pipeline architecture.
All step logic is now in src/pipeline/steps/.
"""
import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import Pipeline


def main():
    """Main pipeline execution."""
    parser = argparse.ArgumentParser(
        description="Intelligent training data generation pipeline"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/launch.yml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--skip-parse",
        action="store_true",
        help="Skip parsing step (use existing symbols.jsonl)"
    )
    parser.add_argument(
        "--skip-question-answer",
        dest="skip_question_answer",
        action="store_true",
        help="Disable question/answer auto mode (use user-provided inputs)"
    )
    parser.add_argument(
        "--skip-auto",
        dest="skip_question_answer",
        action="store_true",
        help="Deprecated alias for --skip-question-answer"
    )
    parser.add_argument(
        "--skip-auto-design-questions",
        action="store_true",
        help="Skip auto design question generation"
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip all LLM generation (QA + design)"
    )
    parser.add_argument(
        "--skip-qa",
        action="store_true",
        help="Skip QA generation"
    )
    parser.add_argument(
        "--skip-design",
        action="store_true",
        help="Skip design generation"
    )
    parser.add_argument(
        "--skip-dedup",
        action="store_true",
        help="Skip deduplication step"
    )
    parser.add_argument(
        "--skip-safety",
        action="store_true",
        help="Skip safety scan step"
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip final export step"
    )
    
    args = parser.parse_args()
    
    # Create and run pipeline
    pipeline = Pipeline(args.config)
    pipeline.run(args)


if __name__ == "__main__":
    main()
