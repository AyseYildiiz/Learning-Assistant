from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from learning_assistant.ks_gateway import KSGatewayClient
from learning_assistant.pdf_extract import extract_text
from learning_assistant.question_generation import generate_multiple_choice_questions


def run_pipeline(
    pdf_path: Path,
    count: int = 5,
    model: str | None = None,
    client: KSGatewayClient | None = None,
) -> dict[str, object]:
    extracted_text = extract_text(pdf_path)
    if not extracted_text.strip():
        raise ValueError(f"No extractable text was found in: {pdf_path}")

    questions = generate_multiple_choice_questions(
        paragraph=extracted_text,
        count=count,
        client=client,
        model=model,
    )
    return {
        "source_pdf": str(pdf_path),
        "question_count": count,
        "questions": [question.model_dump() for question in questions],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="learning-assistant",
        description="Extract text from a PDF and generate multiple-choice questions.",
    )
    parser.add_argument("pdf_path", type=Path, help="Path to the source PDF file.")
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of questions to generate.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional KS AI Gateway model override.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_pipeline(
        pdf_path=args.pdf_path,
        count=args.count,
        model=args.model,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())