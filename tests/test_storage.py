from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from learning_assistant.ks_gateway import MultipleChoiceQuestion
from learning_assistant.storage import (
    SQLiteRepository,
    save_generated_question_with_flashcard,
)


def test_repository_saves_question_and_returns_due_flashcards(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        question = repository.save_question(
            source_pdf="chapter-1.pdf",
            question_text="What is the capital of France?",
            options=["Berlin", "Madrid", "Paris", "Rome"],
            correct_index=2,
        )
        repository.save_flashcard(
            question_id=question.id,
            box_level=1,
            next_review_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        repository.save_flashcard(
            question_id=question.id,
            box_level=2,
            next_review_at=datetime.now(UTC) + timedelta(days=1),
        )

        due_flashcards = repository.get_due_flashcards()
    finally:
        repository.close()

    assert question.id == 1
    assert question.options == ["Berlin", "Madrid", "Paris", "Rome"]
    assert len(due_flashcards) == 1
    assert due_flashcards[0].front_text == "What is the capital of France?"
    assert due_flashcards[0].back_text == "Paris"
    assert due_flashcards[0].box_level == 1


def test_save_generated_question_with_flashcard_creates_new_card(
    tmp_path: Path,
) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    generated_question = MultipleChoiceQuestion(
        question="Which planet is known as the Red Planet?",
        options=["Earth", "Mars", "Venus", "Jupiter"],
        correct_index=1,
    )

    try:
        question_record, flashcard_record = save_generated_question_with_flashcard(
            repository=repository,
            source_pdf=Path("solar-system.pdf"),
            question=generated_question,
            now=now,
        )
        due_flashcards = repository.get_due_flashcards(as_of=now)
    finally:
        repository.close()

    assert question_record.question_text == generated_question.question
    assert question_record.source_pdf == "solar-system.pdf"
    assert flashcard_record.question_id == question_record.id
    assert flashcard_record.box_level == 1
    assert flashcard_record.next_review_at == now
    assert len(due_flashcards) == 1
    assert due_flashcards[0].front_text == generated_question.question
    assert due_flashcards[0].back_text == "Mars"


def test_update_flashcard_review_advances_and_resets_boxes(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    reviewed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    try:
        flashcard = repository.save_flashcard(
            question_id=1,
            box_level=1,
            next_review_at=reviewed_at,
        )

        promoted_flashcard = repository.update_flashcard_review(
            flashcard_id=flashcard.id,
            correct=True,
            reviewed_at=reviewed_at,
        )
        reset_flashcard = repository.update_flashcard_review(
            flashcard_id=flashcard.id,
            correct=False,
            reviewed_at=reviewed_at,
        )
    finally:
        repository.close()

    assert promoted_flashcard.box_level == 2
    assert promoted_flashcard.next_review_at == reviewed_at + timedelta(days=3)
    assert reset_flashcard.box_level == 1
    assert reset_flashcard.next_review_at == reviewed_at + timedelta(days=1)
