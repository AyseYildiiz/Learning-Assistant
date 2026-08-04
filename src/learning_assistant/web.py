from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from learning_assistant.storage import DueFlashcardRecord, SQLiteRepository

app = FastAPI(title="Learning Assistant")
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)
_DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "learning_assistant.sqlite3"
)


def get_repository(request: Request) -> SQLiteRepository:
    repository = getattr(request.app.state, "repository", None)
    if isinstance(repository, SQLiteRepository):
        return repository

    created_repository = SQLiteRepository(_DEFAULT_DATABASE_PATH)
    request.app.state.repository = created_repository
    return created_repository


@app.get("/health")
def health() -> dict[str, str]:
    return {"message": "Hello, world"}


@app.get("/", response_class=HTMLResponse)
def home_page(
    request: Request,
    repository: SQLiteRepository = Depends(get_repository),  # noqa: B008
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"source_pdfs": repository.get_source_pdfs()},
    )


@app.get("/quiz/{pdf_id:path}", response_class=HTMLResponse)
def quiz_page(
    request: Request,
    pdf_id: str,
    repository: SQLiteRepository = Depends(get_repository),  # noqa: B008
) -> HTMLResponse:
    flashcard = _next_flashcard(repository, pdf_id)
    return _render_quiz_page(
        request=request,
        pdf_id=pdf_id,
        flashcard=flashcard,
        correct_count=0,
        incorrect_count=0,
        feedback_message=None,
        completed=flashcard is None,
    )


@app.post("/quiz/{pdf_id:path}/answer", response_class=HTMLResponse)
def answer_question(
    request: Request,
    pdf_id: str,
    flashcard_id: int = Form(...),
    selected_index: int = Form(...),
    correct_count: int = Form(0),
    incorrect_count: int = Form(0),
    repository: SQLiteRepository = Depends(get_repository),  # noqa: B008
) -> HTMLResponse:
    flashcard = repository.get_flashcard_by_id(flashcard_id)
    if flashcard is None or flashcard.source_pdf != pdf_id:
        raise HTTPException(status_code=404, detail="Flashcard not found")

    is_correct = selected_index == flashcard.correct_index
    repository.update_flashcard_review(flashcard_id=flashcard_id, correct=is_correct)

    if is_correct:
        correct_count += 1
        feedback_message = "Correct answer."
    else:
        incorrect_count += 1
        feedback_message = f"Incorrect. Correct answer: {flashcard.back_text}"

    next_flashcard = _next_flashcard(repository, pdf_id)
    return _render_quiz_page(
        request=request,
        pdf_id=pdf_id,
        flashcard=next_flashcard,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        feedback_message=feedback_message,
        completed=next_flashcard is None,
    )


def _next_flashcard(
    repository: SQLiteRepository, pdf_id: str
) -> DueFlashcardRecord | None:
    flashcards = repository.get_due_flashcards_for_source_pdf(pdf_id)
    if not flashcards:
        return None

    return flashcards[0]


def _render_quiz_page(
    *,
    request: Request,
    pdf_id: str,
    flashcard: DueFlashcardRecord | None,
    correct_count: int,
    incorrect_count: int,
    feedback_message: str | None,
    completed: bool,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="quiz.html",
        context={
            "pdf_id": pdf_id,
            "answer_url": f"/quiz/{quote(pdf_id, safe='')}/answer",
            "flashcard": flashcard,
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "feedback_message": feedback_message,
            "completed": completed,
        },
    )
