from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from learning_assistant.main import app
from learning_assistant.storage import SQLiteRepository


def test_quiz_flow_advances_with_htmx_partial_updates(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "quiz.db")
    first_question = repository.save_question(
        source_pdf="chapter-1.pdf",
        question_text="What is 2 + 2?",
        options=["1", "2", "4", "8"],
        correct_index=2,
    )
    second_question = repository.save_question(
        source_pdf="chapter-1.pdf",
        question_text="Which planet is known as the Red Planet?",
        options=["Earth", "Mars", "Venus", "Jupiter"],
        correct_index=1,
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    first_flashcard = repository.save_flashcard(
        question_id=first_question.id,
        box_level=1,
        next_review_at=now,
    )
    second_flashcard = repository.save_flashcard(
        question_id=second_question.id,
        box_level=1,
        next_review_at=now,
    )

    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        with TestClient(app) as client:
            page_response = client.get("/quiz/chapter-1.pdf")
            assert page_response.status_code == 200
            assert "What is 2 + 2?" in page_response.text
            assert 'hx-post="/quiz/chapter-1.pdf/answer"' in page_response.text

            first_answer_response = client.post(
                "/quiz/chapter-1.pdf/answer",
                data={
                    "flashcard_id": str(first_flashcard.id),
                    "selected_index": "2",
                    "correct_count": "0",
                    "incorrect_count": "0",
                },
            )
            assert first_answer_response.status_code == 200
            assert "Correct answer." in first_answer_response.text
            assert (
                "Which planet is known as the Red Planet?" in first_answer_response.text
            )

            second_answer_response = client.post(
                "/quiz/chapter-1.pdf/answer",
                data={
                    "flashcard_id": str(second_flashcard.id),
                    "selected_index": "0",
                    "correct_count": "1",
                    "incorrect_count": "0",
                },
            )
            assert second_answer_response.status_code == 200
            assert "Quiz complete." in second_answer_response.text
            assert "Final score: 1 correct, 1 incorrect." in second_answer_response.text
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository
