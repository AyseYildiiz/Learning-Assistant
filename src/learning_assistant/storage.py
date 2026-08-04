from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from learning_assistant.ks_gateway import MultipleChoiceQuestion

_LEITNER_INTERVALS_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30)


@dataclass(slots=True)
class QuestionRecord:
    id: int
    source_pdf: str
    question_text: str
    options: list[str]
    correct_index: int


@dataclass(slots=True)
class FlashcardRecord:
    id: int
    question_id: int
    box_level: int
    next_review_at: datetime


@dataclass(slots=True)
class DueFlashcardRecord:
    flashcard_id: int
    question_id: int
    source_pdf: str
    question_text: str
    options: list[str]
    correct_index: int
    box_level: int
    next_review_at: datetime
    front_text: str
    back_text: str


class SQLiteRepository:
    def __init__(self, db_path: str | Path) -> None:
        db_path_text = str(db_path)
        if db_path_text != ":memory:":
            Path(db_path_text).parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(db_path_text)
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def close(self) -> None:
        self._connection.close()

    def save_question(
        self,
        source_pdf: str | Path,
        question_text: str,
        options: list[str],
        correct_index: int,
    ) -> QuestionRecord:
        with self._connection:
            return self._insert_question(
                source_pdf=source_pdf,
                question_text=question_text,
                options=options,
                correct_index=correct_index,
            )

    def save_flashcard(
        self,
        question_id: int,
        box_level: int,
        next_review_at: datetime,
    ) -> FlashcardRecord:
        with self._connection:
            return self._insert_flashcard(
                question_id=question_id,
                box_level=box_level,
                next_review_at=next_review_at,
            )

    def update_flashcard_review(
        self,
        flashcard_id: int,
        correct: bool,
        reviewed_at: datetime | None = None,
    ) -> FlashcardRecord:
        current_time = _ensure_utc_datetime(reviewed_at or datetime.now(UTC))
        row = self._connection.execute(
            """
            SELECT question_id, box_level
            FROM flashcards
            WHERE id = ?
            """,
            (flashcard_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"Flashcard {flashcard_id} does not exist")

        current_box_level = int(row["box_level"])
        next_box_level, next_review_at = _calculate_leitner_schedule(
            current_box_level=current_box_level,
            correct=correct,
            reviewed_at=current_time,
        )

        with self._connection:
            self._connection.execute(
                """
                UPDATE flashcards
                SET box_level = ?, next_review_at = ?
                WHERE id = ?
                """,
                (
                    next_box_level,
                    _serialize_datetime(next_review_at),
                    flashcard_id,
                ),
            )

        return FlashcardRecord(
            id=flashcard_id,
            question_id=int(row["question_id"]),
            box_level=next_box_level,
            next_review_at=next_review_at,
        )

    def get_due_flashcards(
        self,
        as_of: datetime | None = None,
    ) -> list[DueFlashcardRecord]:
        reference_time = _ensure_utc_datetime(as_of or datetime.now(UTC))
        rows = self._connection.execute(
            """
            SELECT
                flashcards.id AS flashcard_id,
                flashcards.question_id,
                flashcards.box_level,
                flashcards.next_review_at,
                questions.source_pdf,
                questions.question_text,
                questions.options,
                questions.correct_index
            FROM flashcards
            JOIN questions ON questions.id = flashcards.question_id
            WHERE flashcards.next_review_at <= ?
            ORDER BY flashcards.next_review_at ASC, flashcards.id ASC
            """,
            (_serialize_datetime(reference_time),),
        ).fetchall()

        due_flashcards: list[DueFlashcardRecord] = []
        for row in rows:
            options = _deserialize_options(row["options"])
            correct_index = int(row["correct_index"])
            due_flashcards.append(
                DueFlashcardRecord(
                    flashcard_id=int(row["flashcard_id"]),
                    question_id=int(row["question_id"]),
                    source_pdf=str(row["source_pdf"]),
                    question_text=str(row["question_text"]),
                    options=options,
                    correct_index=correct_index,
                    box_level=int(row["box_level"]),
                    next_review_at=_parse_datetime(str(row["next_review_at"])),
                    front_text=str(row["question_text"]),
                    back_text=options[correct_index],
                )
            )

        return due_flashcards

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_pdf TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    options TEXT NOT NULL,
                    correct_index INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS flashcards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id INTEGER NOT NULL,
                    box_level INTEGER NOT NULL,
                    next_review_at TEXT NOT NULL,
                    FOREIGN KEY (question_id) REFERENCES questions(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_flashcards_due
                    ON flashcards(next_review_at);
                """
            )

    def _insert_question(
        self,
        source_pdf: str | Path,
        question_text: str,
        options: list[str],
        correct_index: int,
    ) -> QuestionRecord:
        normalized_source_pdf = str(source_pdf)
        _validate_question_data(options=options, correct_index=correct_index)

        cursor = self._connection.execute(
            """
            INSERT INTO questions (source_pdf, question_text, options, correct_index)
            VALUES (?, ?, ?, ?)
            """,
            (
                normalized_source_pdf,
                question_text,
                _serialize_options(options),
                correct_index,
            ),
        )

        if cursor.lastrowid is None:
            raise RuntimeError("Failed to persist question record")

        question_id = int(cursor.lastrowid)
        return QuestionRecord(
            id=question_id,
            source_pdf=normalized_source_pdf,
            question_text=question_text,
            options=list(options),
            correct_index=correct_index,
        )

    def _insert_flashcard(
        self,
        question_id: int,
        box_level: int,
        next_review_at: datetime,
    ) -> FlashcardRecord:
        if box_level < 1:
            raise ValueError("box_level must be at least 1")

        normalized_next_review_at = _ensure_utc_datetime(next_review_at)

        cursor = self._connection.execute(
            """
            INSERT INTO flashcards (question_id, box_level, next_review_at)
            VALUES (?, ?, ?)
            """,
            (
                question_id,
                box_level,
                _serialize_datetime(normalized_next_review_at),
            ),
        )

        if cursor.lastrowid is None:
            raise RuntimeError("Failed to persist flashcard record")

        flashcard_id = int(cursor.lastrowid)
        return FlashcardRecord(
            id=flashcard_id,
            question_id=question_id,
            box_level=box_level,
            next_review_at=normalized_next_review_at,
        )


def save_generated_question_with_flashcard(
    repository: SQLiteRepository,
    source_pdf: str | Path,
    question: MultipleChoiceQuestion,
    now: datetime | None = None,
) -> tuple[QuestionRecord, FlashcardRecord]:
    review_time = _ensure_utc_datetime(now or datetime.now(UTC))

    with repository._connection:
        question_record = repository._insert_question(
            source_pdf=source_pdf,
            question_text=question.question,
            options=question.options,
            correct_index=question.correct_index,
        )
        flashcard_record = repository._insert_flashcard(
            question_id=question_record.id,
            box_level=1,
            next_review_at=review_time,
        )

    return question_record, flashcard_record


def _validate_question_data(*, options: list[str], correct_index: int) -> None:
    if not options:
        raise ValueError("options must not be empty")

    if correct_index < 0 or correct_index >= len(options):
        raise ValueError("correct_index must point to a valid option")


def _serialize_options(options: list[str]) -> str:
    return json.dumps(options, ensure_ascii=False)


def _deserialize_options(raw_options: str) -> list[str]:
    options = json.loads(raw_options)
    if not isinstance(options, list):
        raise ValueError("Stored options are not a JSON array")

    return [str(option) for option in options]


def _ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")

    return value.astimezone(UTC)


def _serialize_datetime(value: datetime) -> str:
    return _ensure_utc_datetime(value).isoformat()


def _parse_datetime(raw_value: str) -> datetime:
    parsed_value = datetime.fromisoformat(raw_value)
    return _ensure_utc_datetime(parsed_value)


def _calculate_leitner_schedule(
    *,
    current_box_level: int,
    correct: bool,
    reviewed_at: datetime,
) -> tuple[int, datetime]:
    if current_box_level < 1:
        raise ValueError("current_box_level must be at least 1")

    if correct:
        next_box_level = min(current_box_level + 1, len(_LEITNER_INTERVALS_DAYS))
        delay_days = _LEITNER_INTERVALS_DAYS[next_box_level - 1]
    else:
        next_box_level = 1
        delay_days = 1

    return next_box_level, reviewed_at + timedelta(days=delay_days)