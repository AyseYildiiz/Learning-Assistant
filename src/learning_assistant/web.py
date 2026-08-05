from __future__ import annotations

import contextlib
import os
import random
import re
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from learning_assistant.ks_gateway import KSGatewayClient, LearningPath
from learning_assistant.pdf_extract import extract_text
from learning_assistant.question_generation import (
    answer_chat_message,
    generate_fill_blank_questions,
    generate_learning_path,
    generate_multiple_choice_questions,
)
from learning_assistant.storage import (
    QuestionRecord,
    SQLiteRepository,
    save_generated_fill_blank_with_flashcard,
    save_generated_question_with_flashcard,
)

app = FastAPI(title="Learning Assistant")

_SESSION_SECRET = os.getenv("APP_SESSION_SECRET") or secrets.token_urlsafe(32)

app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
)

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)

_DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "learning_assistant.sqlite3"
)
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_UPLOAD_FILES = 10
_MAX_TOTAL_QUESTIONS = 20
_QUIZ_STATES_KEY = "quiz_states"
_SECONDS_PER_QUESTION = 40
_MIN_QUIZ_SECONDS = 60
_CHAT_HISTORIES_KEY = "chat_histories"
_MAX_CHAT_HISTORY_MESSAGES = 12
_MAX_CHAT_MESSAGE_LENGTH = 2000
_SET_ID_PATTERN = re.compile(
    r"^(?P<stem>.+)-(?P<stamp>\d{14})-(?P<token>[0-9a-f]{4})(?P<ext>\.pdf)$"
)


def get_repository(request: Request) -> SQLiteRepository:
    repository = getattr(request.app.state, "repository", None)
    if isinstance(repository, SQLiteRepository):
        return repository

    repository = SQLiteRepository(_DEFAULT_DATABASE_PATH)
    request.app.state.repository = repository
    return repository


@app.get("/health")
def health() -> dict[str, str]:
    return {"message": "Hello, world"}


@app.get("/", response_class=HTMLResponse)
def home_page(
    request: Request,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> HTMLResponse:
    return _render_home_page(request, repository)


async def _read_pdf_upload(upload: UploadFile) -> tuple[str, bytes]:
    filename = Path(upload.filename or "").name
    if not filename or Path(filename).suffix.lower() != ".pdf":
        raise ValueError("Please select a PDF file.")

    content = await upload.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValueError("The PDF must be smaller than 10 MB.")

    return filename, content


def _extract_pdf_text(content: bytes) -> str:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)

        return extract_text(temporary_path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def _make_set_id(filename: str) -> str:
    stem = Path(filename).stem or "study-set"
    ext = Path(filename).suffix.lower() or ".pdf"
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    token = secrets.token_hex(2)
    return f"{stem}-{timestamp}-{token}{ext}"


def _make_combined_set_id(filenames: list[str]) -> str:
    if len(filenames) == 1:
        return _make_set_id(filenames[0])

    first_stem = Path(filenames[0]).stem or "study-set"
    label = f"{first_stem} + {len(filenames) - 1} more"
    return _make_set_id(f"{label}.pdf")


def _combine_extracted_texts(extracted_texts: list[tuple[str, str]]) -> str:
    if len(extracted_texts) == 1:
        return extracted_texts[0][1]

    sections = [
        f"--- Source: {filename} ---\n{text.strip()}"
        for filename, text in extracted_texts
    ]
    return "\n\n".join(sections)


@app.post("/upload", response_class=HTMLResponse)
async def upload_pdf(
    request: Request,
    files: Annotated[list[UploadFile], File(...)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    mcq_count: Annotated[int, Form()] = 5,
    fill_blank_count: Annotated[int, Form()] = 0,
) -> Response:
    try:
        if not files:
            raise ValueError("Please select at least one PDF file.")
        if len(files) > _MAX_UPLOAD_FILES:
            raise ValueError(f"Choose at most {_MAX_UPLOAD_FILES} PDF files.")

        if mcq_count < 0 or fill_blank_count < 0:
            raise ValueError("Question counts cannot be negative.")

        total_count = mcq_count + fill_blank_count
        if total_count < 1 or total_count > _MAX_TOTAL_QUESTIONS:
            raise ValueError(
                f"Choose between 1 and {_MAX_TOTAL_QUESTIONS} questions in total."
            )

        extracted_texts: list[tuple[str, str]] = []
        for upload in files:
            filename, content = await _read_pdf_upload(upload)
            text = _extract_pdf_text(content)
            if not text.strip():
                raise ValueError(f"No extractable text was found in {filename}.")
            extracted_texts.append((filename, text))

        set_id = _make_combined_set_id([filename for filename, _ in extracted_texts])
        combined_text = _combine_extracted_texts(extracted_texts)
        repository.save_document_text(set_id, combined_text)
        gateway_client = KSGatewayClient()
        try:
            if mcq_count > 0:
                mcq_questions = generate_multiple_choice_questions(
                    paragraph=combined_text,
                    count=mcq_count,
                    client=gateway_client,
                )
                for mcq_question in mcq_questions:
                    save_generated_question_with_flashcard(
                        repository=repository,
                        source_pdf=set_id,
                        question=mcq_question,
                    )

            if fill_blank_count > 0:
                fill_blank_questions = generate_fill_blank_questions(
                    paragraph=combined_text,
                    count=fill_blank_count,
                    client=gateway_client,
                )
                for fill_blank_question in fill_blank_questions:
                    save_generated_fill_blank_with_flashcard(
                        repository=repository,
                        source_pdf=set_id,
                        question=fill_blank_question,
                    )
        finally:
            gateway_client.close()

    except (OSError, ValueError, RuntimeError) as error:
        return _render_home_page(
            request,
            repository,
            error_message=str(error),
            status_code=400,
        )
    finally:
        for upload in files:
            await upload.close()

    return RedirectResponse(url=f"/quiz/{quote(set_id, safe='')}", status_code=303)


def _get_all_questions_or_404(
    repository: SQLiteRepository,
    set_id: str,
) -> list[QuestionRecord]:
    questions = repository.get_questions_for_source_pdf(set_id)
    if not questions:
        raise HTTPException(
            status_code=404, detail="No questions found for this study set."
        )
    return questions


def _get_quiz_states(request: Request) -> dict[str, dict[str, Any]]:
    raw_states = request.session.get(_QUIZ_STATES_KEY, {})
    if isinstance(raw_states, dict):
        return dict(raw_states)
    return {}


def _save_quiz_states(request: Request, states: dict[str, dict[str, Any]]) -> None:
    request.session[_QUIZ_STATES_KEY] = states


def _calculate_quiz_duration_seconds(total_questions: int) -> int:
    return max(total_questions * _SECONDS_PER_QUESTION, _MIN_QUIZ_SECONDS)


def _resolve_deadline_at(
    existing_state: dict[str, Any] | None, total_questions: int
) -> str:
    if existing_state is not None:
        deadline_at = existing_state.get("deadline_at")
        if isinstance(deadline_at, str) and deadline_at:
            return deadline_at

    duration_seconds = _calculate_quiz_duration_seconds(total_questions)
    deadline = datetime.now(UTC) + timedelta(seconds=duration_seconds)
    return deadline.isoformat()


def _current_question_number(total_questions: int, remaining_queue: list[int]) -> int:
    if total_questions <= 0:
        return 0
    distinct_remaining = len(set(remaining_queue))
    return min(total_questions - distinct_remaining + 1, total_questions)


def _create_new_quiz_state(question_ids: list[int]) -> dict[str, Any]:
    total_questions = len(question_ids)
    shuffled_ids = list(question_ids)
    random.shuffle(shuffled_ids)
    return {
        "queue": shuffled_ids,
        "correct_count": 0,
        "incorrect_count": 0,
        "completed": False,
        "total_questions": total_questions,
        "deadline_at": _resolve_deadline_at(None, total_questions),
    }


def _load_or_initialize_quiz_state(
    request: Request,
    set_id: str,
    question_ids: list[int],
) -> dict[str, Any]:
    states = _get_quiz_states(request)
    existing_state = states.get(set_id)
    valid_ids = set(question_ids)

    if isinstance(existing_state, dict) and not bool(
        existing_state.get("completed", False)
    ):
        queue = [
            int(item)
            for item in existing_state.get("queue", [])
            if int(item) in valid_ids
        ]
        if queue:
            total_questions = int(
                existing_state.get("total_questions", len(question_ids))
            )
            state = {
                "queue": queue,
                "correct_count": int(existing_state.get("correct_count", 0)),
                "incorrect_count": int(existing_state.get("incorrect_count", 0)),
                "completed": False,
                "total_questions": total_questions,
                "deadline_at": _resolve_deadline_at(existing_state, total_questions),
            }
            states[set_id] = state
            _save_quiz_states(request, states)
            return state

    state = _create_new_quiz_state(question_ids)
    states[set_id] = state
    _save_quiz_states(request, states)
    return state


def _score_out_of_100(correct_count: int, incorrect_count: int) -> int:
    total_attempts = correct_count + incorrect_count
    if total_attempts <= 0:
        return 0
    return round(correct_count / total_attempts * 100)


@app.get("/quiz/{pdf_id:path}", response_class=HTMLResponse)
def quiz_page(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> HTMLResponse:
    questions = _get_all_questions_or_404(repository, pdf_id)
    question_map = {question.id: question for question in questions}
    state = _load_or_initialize_quiz_state(
        request, pdf_id, [question.id for question in questions]
    )

    queue: list[int] = [
        question_id for question_id in state["queue"] if question_id in question_map
    ]
    if not queue:
        score = _score_out_of_100(state["correct_count"], state["incorrect_count"])
        state["completed"] = True
        states = _get_quiz_states(request)
        states[pdf_id] = state
        _save_quiz_states(request, states)
        return _render_quiz_page(
            request=request,
            pdf_id=pdf_id,
            question=None,
            correct_count=state["correct_count"],
            incorrect_count=state["incorrect_count"],
            feedback_message=None,
            completed=True,
            score_out_of_100=score,
            total_questions=state["total_questions"],
            current_question_number=state["total_questions"],
            quiz_deadline_iso=None,
        )

    return _render_quiz_page(
        request=request,
        pdf_id=pdf_id,
        question=question_map[queue[0]],
        correct_count=state["correct_count"],
        incorrect_count=state["incorrect_count"],
        feedback_message=None,
        completed=False,
        score_out_of_100=None,
        total_questions=state["total_questions"],
        current_question_number=_current_question_number(
            state["total_questions"], queue
        ),
        quiz_deadline_iso=state.get("deadline_at"),
    )


@app.post("/quiz/{pdf_id:path}/restart")
def restart_quiz(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> RedirectResponse:
    questions = _get_all_questions_or_404(repository, pdf_id)
    states = _get_quiz_states(request)
    states[pdf_id] = _create_new_quiz_state([question.id for question in questions])
    _save_quiz_states(request, states)
    return RedirectResponse(url=f"/quiz/{quote(pdf_id, safe='')}", status_code=303)


@app.post("/quiz/{pdf_id:path}/timeout", response_class=HTMLResponse)
def timeout_quiz(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> HTMLResponse:
    questions = _get_all_questions_or_404(repository, pdf_id)
    states = _get_quiz_states(request)
    existing_state = states.get(pdf_id)
    state = (
        existing_state
        if isinstance(existing_state, dict)
        else _create_new_quiz_state([question.id for question in questions])
    )

    state["completed"] = True
    states[pdf_id] = state
    _save_quiz_states(request, states)

    correct_count = int(state.get("correct_count", 0))
    incorrect_count = int(state.get("incorrect_count", 0))
    total_questions = int(state.get("total_questions", len(questions)))
    score = _score_out_of_100(correct_count, incorrect_count)
    return _render_quiz_page(
        request=request,
        pdf_id=pdf_id,
        question=None,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        feedback_message="Time's up.",
        completed=True,
        score_out_of_100=score,
        total_questions=total_questions,
        current_question_number=total_questions,
        quiz_deadline_iso=None,
    )


@app.get("/flashcards/{pdf_id:path}", response_class=HTMLResponse)
def flashcards_page(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> HTMLResponse:
    flashcards = repository.get_all_flashcards_for_source_pdf(pdf_id)

    return templates.TemplateResponse(
        request=request,
        name="flashcards.html",
        context={
            "pdf_id": pdf_id,
            "display_name": _set_display_name(pdf_id),
            "flashcards": flashcards,
            "learning_path_url": f"/learning-path/{quote(pdf_id, safe='')}",
            "chat_history": _get_chat_history(request, pdf_id),
        },
    )


def _build_learning_path_source_material(
    repository: SQLiteRepository,
    pdf_id: str,
    questions: list[QuestionRecord],
) -> str:
    document_text = repository.get_document_text(pdf_id)
    if document_text:
        return document_text

    lines = [
        f"{question.question_text} Answer: {question.options[question.correct_index]}"
        for question in questions
    ]
    return "\n".join(lines)


def _generate_and_save_learning_path(
    repository: SQLiteRepository, pdf_id: str
) -> LearningPath:
    questions = _get_all_questions_or_404(repository, pdf_id)
    source_material = _build_learning_path_source_material(
        repository, pdf_id, questions
    )
    gateway_client = KSGatewayClient()
    try:
        learning_path = generate_learning_path(
            paragraph=source_material, client=gateway_client
        )
    finally:
        gateway_client.close()
    repository.save_learning_path(pdf_id, learning_path.model_dump_json())
    return learning_path


def _get_or_generate_learning_path(
    repository: SQLiteRepository, pdf_id: str
) -> LearningPath:
    existing_record = repository.get_learning_path(pdf_id)
    if existing_record is not None:
        return LearningPath.model_validate_json(existing_record.content_json)
    return _generate_and_save_learning_path(repository, pdf_id)


def _render_learning_path_page(
    request: Request,
    pdf_id: str,
    learning_path: LearningPath | None,
    *,
    error_message: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="learning_path.html",
        context={
            "pdf_id": pdf_id,
            "display_name": _set_display_name(pdf_id),
            "learning_path": learning_path,
            "error_message": error_message,
            "regenerate_url": f"/learning-path/{quote(pdf_id, safe='')}/regenerate",
            "chat_history": _get_chat_history(request, pdf_id),
        },
    )


@app.get("/learning-path/{pdf_id:path}", response_class=HTMLResponse)
def learning_path_page(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> HTMLResponse:
    _get_all_questions_or_404(repository, pdf_id)
    try:
        learning_path = _get_or_generate_learning_path(repository, pdf_id)
    except (OSError, ValueError, RuntimeError) as error:
        return _render_learning_path_page(
            request, pdf_id, None, error_message=str(error)
        )

    return _render_learning_path_page(request, pdf_id, learning_path)


@app.post("/learning-path/{pdf_id:path}/regenerate")
def regenerate_learning_path(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> RedirectResponse:
    _get_all_questions_or_404(repository, pdf_id)
    with contextlib.suppress(OSError, ValueError, RuntimeError):
        _generate_and_save_learning_path(repository, pdf_id)

    return RedirectResponse(
        url=f"/learning-path/{quote(pdf_id, safe='')}", status_code=303
    )


def _get_chat_history(request: Request, pdf_id: str) -> list[dict[str, str]]:
    raw_histories = request.session.get(_CHAT_HISTORIES_KEY, {})
    if not isinstance(raw_histories, dict):
        return []

    raw_history = raw_histories.get(pdf_id, [])
    if not isinstance(raw_history, list):
        return []

    return [
        {"role": str(item["role"]), "content": str(item["content"])}
        for item in raw_history
        if isinstance(item, dict) and "role" in item and "content" in item
    ]


def _save_chat_history(
    request: Request, pdf_id: str, history: list[dict[str, str]]
) -> None:
    raw_histories = request.session.get(_CHAT_HISTORIES_KEY, {})
    histories = dict(raw_histories) if isinstance(raw_histories, dict) else {}
    histories[pdf_id] = history[-_MAX_CHAT_HISTORY_MESSAGES:]
    request.session[_CHAT_HISTORIES_KEY] = histories


@app.post("/chat/{pdf_id:path}", response_class=HTMLResponse)
def chat_with_ai(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    message: Annotated[str, Form(...)],
) -> HTMLResponse:
    trimmed_message = message.strip()[:_MAX_CHAT_MESSAGE_LENGTH]
    if not trimmed_message:
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    questions = _get_all_questions_or_404(repository, pdf_id)
    source_material = _build_learning_path_source_material(
        repository, pdf_id, questions
    )
    history = _get_chat_history(request, pdf_id)

    gateway_client = KSGatewayClient()
    try:
        assistant_reply = answer_chat_message(
            source_material=source_material,
            history=[(item["role"], item["content"]) for item in history],
            question=trimmed_message,
            client=gateway_client,
        )
    except (OSError, ValueError, RuntimeError) as error:
        assistant_reply = f"Sorry, I could not answer that: {error}"
    finally:
        gateway_client.close()

    history.append({"role": "user", "content": trimmed_message})
    history.append({"role": "assistant", "content": assistant_reply})
    _save_chat_history(request, pdf_id, history)

    return templates.TemplateResponse(
        request=request,
        name="chat_message_fragment.html",
        context={
            "user_message": trimmed_message,
            "assistant_reply": assistant_reply,
        },
    )


@app.post("/quiz/{pdf_id:path}/answer", response_class=HTMLResponse)
def answer_question(
    request: Request,
    pdf_id: str,
    question_id: Annotated[int, Form(...)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    selected_index: Annotated[int | None, Form()] = None,
    answer_text: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    questions = _get_all_questions_or_404(repository, pdf_id)
    question_map = {question.id: question for question in questions}
    state = _load_or_initialize_quiz_state(
        request, pdf_id, [question.id for question in questions]
    )

    question = question_map.get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    queue: list[int] = [qid for qid in state["queue"] if qid in question_map]
    if question_id in queue:
        queue.remove(question_id)

    correct_answer = question.options[question.correct_index]
    if question.question_type == "fill_blank":
        if answer_text is None:
            raise HTTPException(
                status_code=422, detail="answer_text is required for this question"
            )
        is_correct = answer_text.strip().casefold() == correct_answer.strip().casefold()
    else:
        if selected_index is None:
            raise HTTPException(
                status_code=422, detail="selected_index is required for this question"
            )
        is_correct = selected_index == question.correct_index

    if is_correct:
        state["correct_count"] += 1
        feedback_message = "Correct answer."
    else:
        state["incorrect_count"] += 1
        feedback_message = f"Incorrect. Correct answer: {correct_answer}"
        queue.append(question_id)

    flashcard = repository.get_flashcard_by_question_id(question_id)
    if flashcard:
        repository.update_flashcard_review(
            flashcard_id=flashcard.id,
            correct=is_correct,
        )

    state["queue"] = queue
    state["completed"] = not queue
    states = _get_quiz_states(request)
    states[pdf_id] = state
    _save_quiz_states(request, states)

    total_questions = state["total_questions"]
    if state["completed"]:
        score = _score_out_of_100(state["correct_count"], state["incorrect_count"])
        return _render_quiz_page(
            request=request,
            pdf_id=pdf_id,
            question=None,
            correct_count=state["correct_count"],
            incorrect_count=state["incorrect_count"],
            feedback_message=feedback_message,
            completed=True,
            score_out_of_100=score,
            total_questions=total_questions,
            current_question_number=total_questions,
            quiz_deadline_iso=None,
        )

    next_question = question_map[queue[0]]
    return _render_quiz_page(
        request=request,
        pdf_id=pdf_id,
        question=next_question,
        correct_count=state["correct_count"],
        incorrect_count=state["incorrect_count"],
        feedback_message=feedback_message,
        completed=False,
        score_out_of_100=None,
        total_questions=total_questions,
        current_question_number=_current_question_number(total_questions, queue),
        quiz_deadline_iso=state.get("deadline_at"),
    )


@app.post("/sets/{pdf_id:path}/delete", response_class=HTMLResponse)
def delete_set(
    request: Request,
    pdf_id: str,
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
) -> HTMLResponse:
    deleted = repository.delete_set(pdf_id)

    states = _get_quiz_states(request)
    if pdf_id in states:
        del states[pdf_id]
        _save_quiz_states(request, states)

    if deleted:
        return _render_home_page(
            request,
            repository,
            success_message="Study set deleted.",
        )

    return _render_home_page(
        request,
        repository,
        error_message="Study set not found.",
        status_code=404,
    )


def _is_htmx_request(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def _render_quiz_page(
    *,
    request: Request,
    pdf_id: str,
    question: QuestionRecord | None,
    correct_count: int,
    incorrect_count: int,
    feedback_message: str | None,
    completed: bool,
    score_out_of_100: int | None,
    total_questions: int = 0,
    current_question_number: int = 0,
    quiz_deadline_iso: str | None = None,
) -> HTMLResponse:
    # HTMX answer/restart requests only ever swap #quiz-panel, so they must
    # get the bare panel fragment. Returning the full quiz.html document here
    # would nest an entire new page (including the theme toggle button and
    # page padding) inside the previous one on every answer.
    template_name = "quiz_panel.html" if _is_htmx_request(request) else "quiz.html"
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "pdf_id": pdf_id,
            "display_name": _set_display_name(pdf_id),
            "answer_url": f"/quiz/{quote(pdf_id, safe='')}/answer",
            "restart_url": f"/quiz/{quote(pdf_id, safe='')}/restart",
            "timeout_url": f"/quiz/{quote(pdf_id, safe='')}/timeout",
            "learning_path_url": f"/learning-path/{quote(pdf_id, safe='')}",
            "question": question,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "feedback_message": feedback_message,
            "completed": completed,
            "score_out_of_100": score_out_of_100,
            "stack_depth": min(correct_count + incorrect_count, 2),
            "total_questions": total_questions,
            "current_question_number": current_question_number,
            "quiz_deadline_iso": quiz_deadline_iso,
            "chat_history": _get_chat_history(request, pdf_id),
        },
    )


def _set_display_name(set_id: str) -> str:
    match = _SET_ID_PATTERN.fullmatch(set_id)
    if not match:
        return set_id

    stamp = match.group("stamp")
    formatted_stamp = (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[8:10]}:{stamp[10:12]}"
    )
    return f"{match.group('stem')}{match.group('ext')} ({formatted_stamp})"


def _study_set_view_models(source_pdfs: list[str]) -> list[dict[str, str]]:
    return [
        {
            "id": source_pdf,
            "name": _set_display_name(source_pdf),
            "encoded_id": quote(source_pdf, safe=""),
        }
        for source_pdf in source_pdfs
    ]


def _render_home_page(
    request: Request,
    repository: SQLiteRepository,
    *,
    error_message: str | None = None,
    success_message: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "study_sets": _study_set_view_models(repository.get_source_pdfs()),
            "error_message": error_message,
            "success_message": success_message,
        },
    )

    response.status_code = status_code
    return response
