from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from learning_assistant.ks_gateway import FillBlankQuestion, MultipleChoiceQuestion

_LEITNER_INTERVALS_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30)


@dataclass(slots=True)
class QuestionRecord:
    id: int
    source_pdf: str
    question_text: str
    options: list[str]
    correct_index: int
    question_type: str = "multiple_choice"


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


@dataclass(slots=True)
class LearningPathRecord:
    id: int
    source_pdf: str
    content_json: str
    created_at: datetime


@dataclass(slots=True)
class UserRecord:
    id: int
    username: str
    password_hash: str
    salt: str
    created_at: datetime


class SQLiteRepository:
    def __init__(self, db_path: str | Path) -> None:
        db_path_text = str(db_path)
        if db_path_text != ":memory:":
            Path(db_path_text).parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(db_path_text, check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys = ON")
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
        question_type: str = "multiple_choice",
    ) -> QuestionRecord:
        with self._connection:
            return self._insert_question(
                source_pdf=source_pdf,
                question_text=question_text,
                options=options,
                correct_index=correct_index,
                question_type=question_type,
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
        return self._fetch_flashcards(as_of=as_of)

    def get_due_flashcards_for_source_pdf(
        self,
        source_pdf: str | Path,
        as_of: datetime | None = None,
    ) -> list[DueFlashcardRecord]:
        return self._fetch_flashcards(
            as_of=as_of,
            source_pdf=str(source_pdf),
        )

    def get_source_pdfs(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT DISTINCT source_pdf FROM questions ORDER BY source_pdf"
        ).fetchall()
        return [str(row["source_pdf"]) for row in rows]

    def get_source_pdfs_for_user(self, user_id: int) -> list[str]:
        rows = self._connection.execute(
            """
            SELECT DISTINCT set_owners.source_pdf
            FROM set_owners
            JOIN questions ON questions.source_pdf = set_owners.source_pdf
            WHERE set_owners.user_id = ?
            ORDER BY set_owners.source_pdf
            """,
            (user_id,),
        ).fetchall()
        return [str(row["source_pdf"]) for row in rows]

    def assign_set_owner(self, source_pdf: str | Path, user_id: int) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO set_owners (source_pdf, user_id)
                VALUES (?, ?)
                ON CONFLICT(source_pdf) DO UPDATE SET user_id = excluded.user_id
                """,
                (str(source_pdf), user_id),
            )

    def get_set_owner_user_id(self, source_pdf: str | Path) -> int | None:
        row = self._connection.execute(
            "SELECT user_id FROM set_owners WHERE source_pdf = ?",
            (str(source_pdf),),
        ).fetchone()
        if row is None:
            return None
        return int(row["user_id"])

    def create_user(
        self,
        username: str,
        password_hash: str,
        salt: str,
        created_at: datetime | None = None,
    ) -> UserRecord:
        created_time = _ensure_utc_datetime(created_at or datetime.now(UTC))
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    INSERT INTO users (username, password_hash, salt, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (username, password_hash, salt, _serialize_datetime(created_time)),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Username '{username}' is already taken") from error

        if cursor.lastrowid is None:
            raise RuntimeError("Failed to persist user record")

        return UserRecord(
            id=int(cursor.lastrowid),
            username=username,
            password_hash=password_hash,
            salt=salt,
            created_at=created_time,
        )

    def get_user_by_username(self, username: str) -> UserRecord | None:
        row = self._connection.execute(
            "SELECT id, username, password_hash, salt, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def get_user_by_id(self, user_id: int) -> UserRecord | None:
        row = self._connection.execute(
            "SELECT id, username, password_hash, salt, created_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def update_user_password(self, user_id: int, password_hash: str, salt: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?
                WHERE id = ?
                """,
                (password_hash, salt, user_id),
            )

    def _row_to_user(self, row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=int(row["id"]),
            username=str(row["username"]),
            password_hash=str(row["password_hash"]),
            salt=str(row["salt"]),
            created_at=_parse_datetime(str(row["created_at"])),
        )

    def delete_set(self, source_pdf: str | Path) -> bool:
        normalized_source_pdf = str(source_pdf)
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM questions WHERE source_pdf = ?",
                (normalized_source_pdf,),
            )
            self._connection.execute(
                "DELETE FROM document_texts WHERE source_pdf = ?",
                (normalized_source_pdf,),
            )
            self._connection.execute(
                "DELETE FROM learning_paths WHERE source_pdf = ?",
                (normalized_source_pdf,),
            )
            self._connection.execute(
                "DELETE FROM set_owners WHERE source_pdf = ?",
                (normalized_source_pdf,),
            )

        return cursor.rowcount > 0

    def get_flashcard_by_id(self, flashcard_id: int) -> DueFlashcardRecord | None:
        row = self._connection.execute(
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
            WHERE flashcards.id = ?
            """,
            (flashcard_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_due_flashcard(row)

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

            CREATE TABLE IF NOT EXISTS document_texts (
                source_pdf TEXT PRIMARY KEY,
                content TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS learning_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_pdf TEXT NOT NULL UNIQUE,
                content_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS set_owners (
                source_pdf TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
            );
            """
            )
            existing_columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(questions)")
            }
            if "question_type" not in existing_columns:
                self._connection.execute(
                    "ALTER TABLE questions ADD COLUMN question_type TEXT "
                    "NOT NULL DEFAULT 'multiple_choice'"
                )

    def _fetch_flashcards(
        self,
        as_of: datetime | None = None,
        source_pdf: str | None = None,
    ) -> list[DueFlashcardRecord]:
        reference_time = _ensure_utc_datetime(as_of or datetime.now(UTC))
        query = [
            "SELECT",
            "    flashcards.id AS flashcard_id,",
            "    flashcards.question_id,",
            "    flashcards.box_level,",
            "    flashcards.next_review_at,",
            "    questions.source_pdf,",
            "    questions.question_text,",
            "    questions.options,",
            "    questions.correct_index",
            "FROM flashcards",
            "JOIN questions ON questions.id = flashcards.question_id",
        ]
        parameters: list[object] = []
        where_clauses: list[str] = ["flashcards.next_review_at <= ?"]
        parameters.append(_serialize_datetime(reference_time))

        if source_pdf is not None:
            where_clauses.append("questions.source_pdf = ?")
            parameters.append(source_pdf)

        query.extend(["WHERE", " AND ".join(where_clauses)])
        query.append("ORDER BY flashcards.next_review_at ASC, flashcards.id ASC")

        rows = self._connection.execute("\n".join(query), tuple(parameters)).fetchall()
        return [self._row_to_due_flashcard(row) for row in rows]

    def _row_to_due_flashcard(self, row: sqlite3.Row) -> DueFlashcardRecord:
        options = _deserialize_options(str(row["options"]))
        correct_index = int(row["correct_index"])
        return DueFlashcardRecord(
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

    def _row_to_question(
        self,
        row: sqlite3.Row,
    ) -> QuestionRecord:
        return QuestionRecord(
            id=int(row["id"]),
            source_pdf=str(row["source_pdf"]),
            question_text=str(row["question_text"]),
            options=_deserialize_options(str(row["options"])),
            correct_index=int(row["correct_index"]),
            question_type=str(row["question_type"]),
        )

    def _insert_question(
        self,
        source_pdf: str | Path,
        question_text: str,
        options: list[str],
        correct_index: int,
        question_type: str = "multiple_choice",
    ) -> QuestionRecord:
        normalized_source_pdf = str(source_pdf)
        _validate_question_data(options=options, correct_index=correct_index)

        cursor = self._connection.execute(
            """
            INSERT INTO questions
                (source_pdf, question_text, options, correct_index, question_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                normalized_source_pdf,
                question_text,
                _serialize_options(options),
                correct_index,
                question_type,
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
            question_type=question_type,
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

    def get_all_flashcards_for_source_pdf(
        self,
        source_pdf: str | Path,
    ) -> list[DueFlashcardRecord]:
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
        JOIN questions
            ON questions.id = flashcards.question_id
        WHERE questions.source_pdf = ?
        ORDER BY flashcards.id
        """,
            (str(source_pdf),),
        ).fetchall()
        return [self._row_to_due_flashcard(row) for row in rows]

    def get_questions_for_source_pdf(
        self,
        source_pdf: str | Path,
    ) -> list[QuestionRecord]:
        rows = self._connection.execute(
            """
        SELECT
            id,
            source_pdf,
            question_text,
            options,
            correct_index,
            question_type
        FROM questions
        WHERE source_pdf = ?
        ORDER BY id
        """,
            (str(source_pdf),),
        ).fetchall()

        return [self._row_to_question(row) for row in rows]

    def get_question_by_id(
        self,
        question_id: int,
    ) -> QuestionRecord | None:
        row = self._connection.execute(
            """
        SELECT
            id,
            source_pdf,
            question_text,
            options,
            correct_index,
            question_type
        FROM questions
        WHERE id = ?
        """,
            (question_id,),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_question(row)

    def get_flashcard_by_question_id(
        self,
        question_id: int,
    ) -> FlashcardRecord | None:
        row = self._connection.execute(
            """
        SELECT
            id,
            question_id,
            box_level,
            next_review_at
        FROM flashcards
        WHERE question_id = ?
        """,
            (question_id,),
        ).fetchone()

        if row is None:
            return None

        return FlashcardRecord(
            id=int(row["id"]),
            question_id=int(row["question_id"]),
            box_level=int(row["box_level"]),
            next_review_at=_parse_datetime(str(row["next_review_at"])),
        )

    def save_document_text(self, source_pdf: str | Path, content: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO document_texts (source_pdf, content)
                VALUES (?, ?)
                ON CONFLICT(source_pdf) DO UPDATE SET content = excluded.content
                """,
                (str(source_pdf), content),
            )

    def get_document_text(self, source_pdf: str | Path) -> str | None:
        row = self._connection.execute(
            "SELECT content FROM document_texts WHERE source_pdf = ?",
            (str(source_pdf),),
        ).fetchone()

        if row is None:
            return None

        return str(row["content"])

    def save_learning_path(
        self,
        source_pdf: str | Path,
        content_json: str,
        created_at: datetime | None = None,
    ) -> LearningPathRecord:
        normalized_source_pdf = str(source_pdf)
        created_time = _ensure_utc_datetime(created_at or datetime.now(UTC))

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO learning_paths (source_pdf, content_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source_pdf) DO UPDATE SET
                    content_json = excluded.content_json,
                    created_at = excluded.created_at
                """,
                (
                    normalized_source_pdf,
                    content_json,
                    _serialize_datetime(created_time),
                ),
            )

        learning_path = self.get_learning_path(normalized_source_pdf)
        if learning_path is None:
            raise RuntimeError("Failed to persist learning path record")
        return learning_path

    def get_learning_path(self, source_pdf: str | Path) -> LearningPathRecord | None:
        row = self._connection.execute(
            """
            SELECT id, source_pdf, content_json, created_at
            FROM learning_paths
            WHERE source_pdf = ?
            """,
            (str(source_pdf),),
        ).fetchone()

        if row is None:
            return None

        return LearningPathRecord(
            id=int(row["id"]),
            source_pdf=str(row["source_pdf"]),
            content_json=str(row["content_json"]),
            created_at=_parse_datetime(str(row["created_at"])),
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
            question_type="multiple_choice",
        )
        flashcard_record = repository._insert_flashcard(
            question_id=question_record.id,
            box_level=1,
            next_review_at=review_time,
        )

    return question_record, flashcard_record


def save_generated_fill_blank_with_flashcard(
    repository: SQLiteRepository,
    source_pdf: str | Path,
    question: FillBlankQuestion,
    now: datetime | None = None,
) -> tuple[QuestionRecord, FlashcardRecord]:
    review_time = _ensure_utc_datetime(now or datetime.now(UTC))

    with repository._connection:
        question_record = repository._insert_question(
            source_pdf=source_pdf,
            question_text=question.question,
            options=[question.answer],
            correct_index=0,
            question_type="fill_blank",
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
