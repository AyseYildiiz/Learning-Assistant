from __future__ import annotations

import os
import re
import secrets
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from learning_assistant.ks_gateway import KSGatewayClient
from learning_assistant.pdf_extract import extract_text
from learning_assistant.question_generation import generate_multiple_choice_questions
from learning_assistant.storage import (
    QuestionRecord,
    SQLiteRepository,
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
_QUIZ_STATES_KEY = "quiz_states"
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


def _make_set_id(filename: str) -> str:
    stem = Path(filename).stem or "study-set"
    ext = Path(filename).suffix.lower() or ".pdf"
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    token = secrets.token_hex(2)
    return f"{stem}-{timestamp}-{token}{ext}"


@app.post("/upload", response_class=HTMLResponse)
async def upload_pdf(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
    count: Annotated[int, Form()] = 5,
) -> Response:
    try:
        filename, content = await _read_pdf_upload(file)
        if count < 1 or count > 20:
            raise ValueError("Choose between 1 and 20 questions.")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False
            ) as temporary_file:
                temporary_file.write(content)
                temporary_path = Path(temporary_file.name)

            extracted_text = extract_text(temporary_path)
        finally:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)

        if not extracted_text.strip():
            raise ValueError("No extractable text was found in this PDF.")

        gateway_client = KSGatewayClient()
        try:
            questions = generate_multiple_choice_questions(
                paragraph=extracted_text,
                count=count,
                client=gateway_client,
            )
        finally:
            gateway_client.close()

        set_id = _make_set_id(filename)
        for question in questions:
            save_generated_question_with_flashcard(
                repository=repository,
                source_pdf=set_id,
                question=question,
            )

    except (OSError, ValueError, RuntimeError) as error:
        return _render_home_page(
            request,
            repository,
            error_message=str(error),
            status_code=400,
        )
    finally:
        await file.close()

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


def _create_new_quiz_state(question_ids: list[int]) -> dict[str, Any]:
    return {
        "queue": list(question_ids),
        "correct_count": 0,
        "incorrect_count": 0,
        "completed": False,
        "total_questions": len(question_ids),
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
            state = {
                "queue": queue,
                "correct_count": int(existing_state.get("correct_count", 0)),
                "incorrect_count": int(existing_state.get("incorrect_count", 0)),
                "completed": False,
                "total_questions": int(
                    existing_state.get("total_questions", len(question_ids))
                ),
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
        },
    )


@app.post("/quiz/{pdf_id:path}/answer", response_class=HTMLResponse)
def answer_question(
    request: Request,
    pdf_id: str,
    question_id: Annotated[int, Form(...)],
    selected_index: Annotated[int, Form(...)],
    repository: Annotated[SQLiteRepository, Depends(get_repository)],
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

    is_correct = selected_index == question.correct_index
    if is_correct:
        state["correct_count"] += 1
        feedback_message = "Correct answer."
    else:
        state["incorrect_count"] += 1
        feedback_message = (
            f"Incorrect. Correct answer: {question.options[question.correct_index]}"
        )
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
            "question": question,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "feedback_message": feedback_message,
            "completed": completed,
            "score_out_of_100": score_out_of_100,
            "stack_depth": min(correct_count + incorrect_count, 2),
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
