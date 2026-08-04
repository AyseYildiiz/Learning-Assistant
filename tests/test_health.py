from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from learning_assistant.main import app
from learning_assistant.storage import SQLiteRepository


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, world"}


def test_home_page_lists_stored_source_pdfs(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "home.db")
    repository.save_question(
        source_pdf="my-document.pdf",
        question_text="Question",
        options=["Answer"],
        correct_index=0,
    )
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        response = TestClient(app).get("/")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 200
    assert "my-document.pdf" in response.text


def test_upload_pdf_generates_and_stores_flashcards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SQLiteRepository(tmp_path / "upload.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            return '{"question":"What is tested?","options":["This"],"correct_index":0}'

    def fake_extract_text(path: Path) -> str:
        assert path.exists()
        return "Test material"

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)
    monkeypatch.setattr("learning_assistant.web.extract_text", fake_extract_text)

    try:
        client = TestClient(app)
        response = client.post(
            "/upload",
            files={"file": ("lesson.pdf", b"%PDF-1.7", "application/pdf")},
            data={"count": "1"},
            follow_redirects=False,
        )
        quiz_response = client.get(response.headers["location"])
        flashcards_response = client.get("/flashcards/lesson.pdf")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 303
    assert response.headers["location"] == "/quiz/lesson.pdf"
    assert quiz_response.status_code == 200
    assert "Quiz" in quiz_response.text
    assert "What is tested?" in quiz_response.text
    assert flashcards_response.status_code == 200
    assert "Flashcards" in flashcards_response.text
    assert "What is tested?" in flashcards_response.text
