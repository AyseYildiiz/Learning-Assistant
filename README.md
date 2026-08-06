# Learning Assistant

A FastAPI web app that turns PDFs into active-recall study material: upload one or
more PDFs and get an AI-generated multiple-choice/fill-in-the-blank quiz,
spaced-repetition flashcards, a research-backed learning path, and a chat
widget to ask follow-up questions about the material — all powered by the KS
AI Gateway, with a full English/Turkish UI.

## Features

- **Multi-PDF upload** — select several PDFs at once; their text is combined
  into a single study set, and question generation round-robins across all of
  them so every source is actually covered.
- **Quiz generation** — configurable number of multiple-choice and
  fill-in-the-blank questions, timed quiz session with auto-submit on timeout.
- **Flashcards** — every generated question doubles as a flashcard for
  spaced-repetition style review.
- **Learning path** — an AI-generated overview plus a step-by-step path with
  external resources (docs, courses, articles) for going deeper on each topic,
  cached per study set and regenerable on demand.
- **AI chat widget** — ask free-form questions about the uploaded material,
  answered by the gateway and grounded only in that material.
- **English / Turkish UI** — a language switcher persists the choice in the
  session, translates all page text, and instructs the LLM to answer in the
  selected language.
- **Light/dark theme toggle.**
- **CLI** — generate multiple-choice questions from a single PDF straight from
  the command line, without running the web server.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management and running
  commands
- Access credentials for a KS AI Gateway instance (client id/secret + base
  URL)

## Setup

```powershell
git clone <this-repo>
cd Learning-Assistant
uv sync
```

Create a `.env` file in the project root with your gateway credentials:

```env
KS_CLIENT_ID=your-client-id
KS_CLIENT_SECRET=your-client-secret
KS_BASE_URL=your-gateway-base-url
KS_RESPONSE_LANGUAGE=en-US
```

`KS_RESPONSE_LANGUAGE` is only a default fallback — the web app overrides it
per-request based on the language selected in the UI (`en-US`/`tr-TR`).

## Running the web app

```powershell
uv run uvicorn learning_assistant.main:app --reload
```

Then open `http://127.0.0.1:8000` in a browser, upload one or more PDFs, and
choose how many multiple-choice/fill-in-the-blank questions to generate.

## Using the CLI

Generate multiple-choice questions for a single PDF without the web UI:

```powershell
uv run learning-assistant path\to\file.pdf --count 5
```

Add `--model` to override the default KS AI Gateway model. The result is
printed as JSON to stdout.

## Project structure

```
src/learning_assistant/
  web.py                 FastAPI routes: upload, quiz, flashcards, learning path, chat
  question_generation.py Prompt building + AI-backed question/learning-path generation
  ks_gateway.py           KS AI Gateway HTTP client (auth, infer, streaming parsing)
  pdf_extract.py          PDF text extraction (pypdf)
  storage.py              SQLite repository (questions, flashcards, document text, learning paths)
  i18n.py                 EN/TR translation strings and helpers
  settings.py             Gateway settings loaded from environment/.env
  cli.py                  Command-line entry point
  templates/              Jinja2 templates for every page/fragment
```

## Testing & quality checks

```powershell
uv run ruff format src tests
uv run ruff check src tests
uv run mypy --strict src tests
uv run pytest -q
```

Run all tests with visible output:

```powershell
uv run pytest -s
```

Run the real-file PDF extraction integration test against an actual PDF:

```powershell
$env:REAL_PDF_PATH = "C:\\Users\\KSMATADOR\\Downloads\\sample.pdf"
uv run pytest -s tests/test_pdf_extract.py
```

There is also `tests/test_real_gateway.py`, which exercises the real KS AI
Gateway using the credentials in `.env` (skipped automatically if they aren't
configured).

Note: `.docx` files are not supported by `extract_text`; it currently accepts
only `.pdf` files.
