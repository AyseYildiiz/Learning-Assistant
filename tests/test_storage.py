from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from learning_assistant.ks_gateway import FillBlankQuestion, MultipleChoiceQuestion
from learning_assistant.storage import (
    SQLiteRepository,
    save_generated_fill_blank_with_flashcard,
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


def test_save_generated_fill_blank_with_flashcard_creates_new_card(
    tmp_path: Path,
) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    generated_question = FillBlankQuestion(
        question="Photosynthesis converts light into _____ energy.",
        answer="chemical",
    )

    try:
        question_record, flashcard_record = save_generated_fill_blank_with_flashcard(
            repository=repository,
            source_pdf=Path("biology.pdf"),
            question=generated_question,
            now=now,
        )
    finally:
        repository.close()

    assert question_record.question_type == "fill_blank"
    assert question_record.options == ["chemical"]
    assert question_record.correct_index == 0
    assert flashcard_record.question_id == question_record.id


def test_document_text_round_trip(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        assert repository.get_document_text("chapter-1.pdf") is None

        repository.save_document_text("chapter-1.pdf", "Original extracted text.")
        repository.save_document_text("chapter-1.pdf", "Updated extracted text.")

        stored_text = repository.get_document_text("chapter-1.pdf")
    finally:
        repository.close()

    assert stored_text == "Updated extracted text."


def test_learning_path_round_trip(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    try:
        assert repository.get_learning_path("chapter-1.pdf") is None

        first_record = repository.save_learning_path(
            "chapter-1.pdf", '{"overview": "v1", "steps": []}', now
        )
        second_record = repository.save_learning_path(
            "chapter-1.pdf", '{"overview": "v2", "steps": []}', now
        )
        fetched_record = repository.get_learning_path("chapter-1.pdf")
    finally:
        repository.close()

    assert first_record.content_json == '{"overview": "v1", "steps": []}'
    assert second_record.content_json == '{"overview": "v2", "steps": []}'
    assert fetched_record is not None
    assert fetched_record.content_json == '{"overview": "v2", "steps": []}'
    assert fetched_record.source_pdf == "chapter-1.pdf"


def test_update_flashcard_review_advances_and_resets_boxes(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    reviewed_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    try:
        question = repository.save_question(
            source_pdf="chapter-1.pdf",
            question_text="What is 2 + 2?",
            options=["1", "2", "4", "8"],
            correct_index=2,
        )
        flashcard = repository.save_flashcard(
            question_id=question.id,
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


def test_create_user_and_look_up_by_username_and_id(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        created = repository.create_user("alice", "hash", "salt")
        by_username = repository.get_user_by_username("alice")
        by_id = repository.get_user_by_id(created.id)
        unknown_username = repository.get_user_by_username("unknown")
    finally:
        repository.close()

    assert by_username is not None
    assert by_username.id == created.id
    assert by_id is not None
    assert by_id.username == "alice"
    assert unknown_username is None


def test_create_user_rejects_duplicate_username(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        repository.create_user("alice", "hash", "salt")
        try:
            repository.create_user("alice", "other-hash", "other-salt")
            duplicate_raised = False
        except ValueError:
            duplicate_raised = True
    finally:
        repository.close()

    assert duplicate_raised


def test_update_user_password_changes_hash_and_salt(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        created = repository.create_user("alice", "hash", "salt")
        repository.update_user_password(created.id, "new-hash", "new-salt")
        updated = repository.get_user_by_id(created.id)
    finally:
        repository.close()

    assert updated is not None
    assert updated.password_hash == "new-hash"
    assert updated.salt == "new-salt"


def test_set_ownership_scopes_source_pdfs_per_user(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        alice = repository.create_user("alice", "hash", "salt")
        bob = repository.create_user("bob", "hash", "salt")
        repository.save_question(
            source_pdf="alice-set.pdf",
            question_text="Question",
            options=["Answer"],
            correct_index=0,
        )
        repository.save_question(
            source_pdf="bob-set.pdf",
            question_text="Question",
            options=["Answer"],
            correct_index=0,
        )
        repository.assign_set_owner("alice-set.pdf", alice.id)
        repository.assign_set_owner("bob-set.pdf", bob.id)
        alice_sets = repository.get_source_pdfs_for_user(alice.id)
        bob_sets = repository.get_source_pdfs_for_user(bob.id)
        alice_set_owner = repository.get_set_owner_user_id("alice-set.pdf")
        missing_set_owner = repository.get_set_owner_user_id("missing.pdf")
    finally:
        repository.close()

    assert alice_sets == ["alice-set.pdf"]
    assert bob_sets == ["bob-set.pdf"]
    assert alice_set_owner == alice.id
    assert missing_set_owner is None


def test_delete_set_also_removes_set_owner_row(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "study.db")
    try:
        alice = repository.create_user("alice", "hash", "salt")
        repository.save_question(
            source_pdf="alice-set.pdf",
            question_text="Question",
            options=["Answer"],
            correct_index=0,
        )
        repository.assign_set_owner("alice-set.pdf", alice.id)

        deleted = repository.delete_set("alice-set.pdf")
        owner_after_delete = repository.get_set_owner_user_id("alice-set.pdf")
    finally:
        repository.close()

    assert deleted
    assert owner_after_delete is None

