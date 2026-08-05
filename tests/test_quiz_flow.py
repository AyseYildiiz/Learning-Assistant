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
    repository.save_flashcard(
        question_id=first_question.id,
        box_level=1,
        next_review_at=now,
    )
    repository.save_flashcard(
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
                    "question_id": str(first_question.id),
                    "selected_index": "2",
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
                    "question_id": str(second_question.id),
                    "selected_index": "0",
                },
            )
            assert second_answer_response.status_code == 200

            completion_response = client.post(
                "/quiz/chapter-1.pdf/answer",
                data={
                    "question_id": str(second_question.id),
                    "selected_index": "1",
                },
            )
            assert completion_response.status_code == 200
            assert "Quiz complete." in completion_response.text
            assert "Final score: 2 correct, 1 incorrect." in completion_response.text
            assert "Score:</strong> 67 / 100" in completion_response.text
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository


def test_quiz_resumes_if_unfinished_and_restarts_if_completed(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "resume.db")
    first_question = repository.save_question(
        source_pdf="session.pdf",
        question_text="Question one?",
        options=["A", "B", "C", "D"],
        correct_index=0,
    )
    second_question = repository.save_question(
        source_pdf="session.pdf",
        question_text="Question two?",
        options=["A", "B", "C", "D"],
        correct_index=1,
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    repository.save_flashcard(
        question_id=first_question.id, box_level=1, next_review_at=now
    )
    repository.save_flashcard(
        question_id=second_question.id, box_level=1, next_review_at=now
    )

    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        with TestClient(app) as client:
            start_response = client.get("/quiz/session.pdf")
            assert start_response.status_code == 200
            assert "Question one?" in start_response.text

            answer_first = client.post(
                "/quiz/session.pdf/answer",
                data={"question_id": str(first_question.id), "selected_index": "0"},
            )
            assert answer_first.status_code == 200
            assert "Question two?" in answer_first.text

            resumed_response = client.get("/quiz/session.pdf")
            assert resumed_response.status_code == 200
            assert "Question two?" in resumed_response.text
            assert "Question one?" not in resumed_response.text

            finish_response = client.post(
                "/quiz/session.pdf/answer",
                data={"question_id": str(second_question.id), "selected_index": "1"},
            )
            assert finish_response.status_code == 200
            assert "Quiz complete." in finish_response.text

            restart_from_completed = client.get("/quiz/session.pdf")
            assert restart_from_completed.status_code == 200
            assert "Question one?" in restart_from_completed.text
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository


def test_htmx_answer_request_returns_bare_panel_fragment(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "fragment.db")
    question = repository.save_question(
        source_pdf="fragment.pdf",
        question_text="What is 2 + 2?",
        options=["1", "2", "4", "8"],
        correct_index=2,
    )
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    repository.save_flashcard(question_id=question.id, box_level=1, next_review_at=now)

    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        with TestClient(app) as client:
            answer_response = client.post(
                "/quiz/fragment.pdf/answer",
                data={"question_id": str(question.id), "selected_index": "2"},
                headers={"HX-Request": "true"},
            )
            assert answer_response.status_code == 200
            assert "<!DOCTYPE html>" not in answer_response.text
            assert 'id="theme-toggle"' not in answer_response.text
            assert 'id="quiz-panel"' in answer_response.text
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository


def test_delete_set_removes_it_from_home_page(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "delete.db")
    repository.save_question(
        source_pdf="old-set.pdf",
        question_text="Delete me?",
        options=["Yes"],
        correct_index=0,
    )

    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        with TestClient(app) as client:
            before_delete = client.get("/")
            assert "old-set.pdf" in before_delete.text

            delete_response = client.post("/sets/old-set.pdf/delete")
            assert delete_response.status_code == 200
            assert "Study set deleted." in delete_response.text

            after_delete = client.get("/")
            assert "old-set.pdf" not in after_delete.text
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository
