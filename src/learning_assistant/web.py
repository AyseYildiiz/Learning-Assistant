from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from learning_assistant.ks_gateway import KSGatewayClient
from learning_assistant.pdf_extract import extract_text
from learning_assistant.question_generation import generate_multiple_choice_questions
from learning_assistant.storage import (
    DueFlashcardRecord,
    SQLiteRepository,
    save_generated_question_with_flashcard,
)

app = FastAPI(title="Learning Assistant")
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)
_DEFAULT_DATABASE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "learning_assistant.sqlite3"
)
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
    return _render_home_page(request, repository)


async def _read_pdf_upload(upload: UploadFile) -> tuple[str, bytes]:
    filename = Path(upload.filename or "").name
    if not filename or Path(filename).suffix.lower() != ".pdf":
        raise ValueError("Please select a PDF file.")

    content = await upload.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValueError("The PDF must be smaller than 10 MB.")

    return filename, content


@app.post("/upload", response_class=HTMLResponse)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    count: int = Form(5),
    repository: SQLiteRepository = Depends(get_repository),  # noqa: B008
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
            if temporary_path is not None:
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

        for question in questions:
            save_generated_question_with_flashcard(
                repository=repository,
                source_pdf=filename,
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

    return RedirectResponse(
        url=f"/quiz/{quote(filename, safe='')}",
        status_code=303,
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


@app.get("/flashcards/{pdf_id:path}", response_class=HTMLResponse)
def flashcards_page(
    request: Request,
    pdf_id: str,
    repository: SQLiteRepository = Depends(get_repository),  # noqa: B008
) -> HTMLResponse:
    flashcards = repository.get_due_flashcards_for_source_pdf(pdf_id)
    return templates.TemplateResponse(
        request=request,
        name="flashcards.html",
        context={"pdf_id": pdf_id, "flashcards": flashcards},
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
            "source_pdfs": repository.get_source_pdfs(),
            "error_message": error_message,
            "success_message": success_message,
        },
    )
    response.status_code = status_code
    return response
