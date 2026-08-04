# Learning Assistant

Privacy classification: KocSistem Internal Sharing.

Learning Assistant is a FastAPI, Jinja2/HTMX, and SQLite web application that
turns uploaded PDF study notes into multiple-choice quizzes and Leitner
flashcards. It calls the KS AI Gateway for structured question generation and
stores generated study sets locally.

Internship metadata:

- Intern: Ayse Yildiz
- Period: 2026-08-03 to 2026-08-31
- Duration: 4 weeks, 20 business days
- Mentor: Muhammed Bilal Kutlu

## Features

- PDF upload and text extraction.
- Multiple-choice quiz generation through the KS AI Gateway.
- Pydantic validation for the LLM JSON output.
- One retry when the gateway returns malformed or schema-invalid JSON.
- SQLite persistence for generated questions and flashcards.
- Leitner scheduling: known cards move to later review boxes, missed cards
  return to box 1.
- Quiz answering flow with correct and incorrect score summary.
- Flashcard review page for due cards.

## Technology

- Python 3.12+
- `uv` for dependency and command management
- FastAPI
- Jinja2 templates with HTMX for quiz answer updates
- SQLite
- `pydantic-settings` for `.env` configuration
- `ruff`, `mypy --strict`, and `pytest`

The import package name is `learning_assistant`. Use the underscore in Python
module paths even though the project name is `learning-assistant`.

## Setup

Install dependencies:

```powershell
uv sync
```

Create a `.env` file in the repository root:

```dotenv
CLIENT_ID=
CLIENT_SECRET=
BASE_URL=https://ai.kocsistem.com.tr/ai-service/gateway/api
```

Do not commit real credentials. `CLIENT_ID` and `CLIENT_SECRET` must only be
provided through environment variables or `.env`.

Run the application:

```powershell
uv run uvicorn learning_assistant.main:app --reload
```

Open the local application at `http://127.0.0.1:8000`.

## Demo Flow

1. Open the home page.
2. Upload a text-based PDF file up to 10 MB.
3. Choose the number of quiz questions.
4. Click `Generate set`.
5. After generation, the app redirects to the quiz page for that PDF.
6. Answer questions and review the score summary.
7. Use `Review flashcards` to inspect due Leitner cards.

## Architecture

- `src/learning_assistant/web.py`: FastAPI routes, upload handling, quiz flow,
  and template rendering.
- `src/learning_assistant/pdf_extract.py`: PDF text extraction.
- `src/learning_assistant/ks_gateway.py`: KS AI Gateway token and infer calls.
- `src/learning_assistant/question_generation.py`: prompt construction, JSON
  parsing, schema validation, and retry behavior.
- `src/learning_assistant/storage.py`: SQLite repository and Leitner schedule
  logic.
- `src/learning_assistant/templates/`: Jinja2 pages and HTMX quiz fragments.
- `tests/`: unit and route tests.

## Quality Gates

Run these before opening a PR:

```powershell
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy
uv run pytest
```

To apply formatting:

```powershell
uv run ruff format src tests
```

Run the real-file PDF extraction integration test by setting an environment
variable to a local PDF:

```powershell
$env:REAL_PDF_PATH = "C:\\Users\\KSMATADOR\\Downloads\\sample.pdf"
uv run pytest -s tests/test_pdf_extract.py
```

## Privacy and Data Rules

- Do not use real personal data in tests, demo PDFs, database fixtures, or
  screenshots.
- Use synthetic or anonymized test material.
- Never log or commit gateway credentials.
- The local SQLite database is for development data only.

## Current Scope

Implemented deliverables cover the week 1 to week 3 functional path:

- PDF to quiz prototype.
- JSON-validated question generation with retry.
- Quiz plus flashcard set persistence.
- Leitner review scheduling.
- Quiz flow and score summary.

The optional fill-in-the-blank question type is not implemented.
