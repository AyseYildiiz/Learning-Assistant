from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from learning_assistant.main import app
from learning_assistant.storage import SQLiteRepository

from conftest import authenticate


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
        client = TestClient(app)
        authenticate(client, repository, "my-document.pdf")
        response = client.get("/")
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

        def infer(
            self, prompt: str, model: str | None = None, language: str | None = None
        ) -> str:
            return '{"question":"What is tested?","options":["This"],"correct_index":0}'

    def fake_extract_text(path: Path) -> str:
        assert path.exists()
        return "Test material"

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)
    monkeypatch.setattr("learning_assistant.web.extract_text", fake_extract_text)

    try:
        client = TestClient(app)
        authenticate(client, repository)
        response = client.post(
            "/upload",
            files={"files": ("lesson.pdf", b"%PDF-1.7", "application/pdf")},
            data={"mcq_count": "1"},
            follow_redirects=False,
        )
        location = response.headers["location"]
        set_id = unquote(location.removeprefix("/quiz/"))
        quiz_response = client.get(response.headers["location"])
        flashcards_response = client.get(f"/flashcards/{set_id}")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 303
    assert response.headers["location"].startswith("/quiz/lesson-")
    assert response.headers["location"].endswith(".pdf")
    assert quiz_response.status_code == 200
    assert "Quiz" in quiz_response.text
    assert "What is tested?" in quiz_response.text
    assert flashcards_response.status_code == 200
    assert "Flashcards" in flashcards_response.text
    assert "What is tested?" in flashcards_response.text


def test_upload_multiple_pdfs_combines_them_into_one_study_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SQLiteRepository(tmp_path / "multi-upload.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    seen_prompts: list[str] = []

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(
            self, prompt: str, model: str | None = None, language: str | None = None
        ) -> str:
            seen_prompts.append(prompt)
            return '{"question":"What is tested?","options":["This"],"correct_index":0}'

    extracted_texts = {
        "chapter-one.pdf": "Chapter one covers photosynthesis.",
        "chapter-two.pdf": "Chapter two covers cellular respiration.",
    }

    def fake_extract_text(path: Path) -> str:
        assert path.exists()
        # NamedTemporaryFile gives every upload a unique path, so track calls by order.
        return extracted_texts[fake_extract_text.filenames.pop(0)]  # type: ignore[attr-defined]

    fake_extract_text.filenames = list(extracted_texts)  # type: ignore[attr-defined]

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)
    monkeypatch.setattr("learning_assistant.web.extract_text", fake_extract_text)

    try:
        client = TestClient(app)
        authenticate(client, repository)
        response = client.post(
            "/upload",
            files=[
                ("files", ("chapter-one.pdf", b"%PDF-1.7", "application/pdf")),
                ("files", ("chapter-two.pdf", b"%PDF-1.7", "application/pdf")),
            ],
            data={"mcq_count": "2"},
            follow_redirects=False,
        )
        location = response.headers["location"]
        set_id = unquote(location.removeprefix("/quiz/"))
        document_text = repository.get_document_text(set_id)
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 303
    assert response.headers["location"].startswith(
        "/quiz/chapter-one%20%2B%201%20more-"
    )
    assert document_text is not None
    assert "Chapter one covers photosynthesis." in document_text
    assert "Chapter two covers cellular respiration." in document_text
    # Question generation round-robins across sources so every uploaded PDF
    # is actually used, instead of the model only drawing from one of them.
    assert len(seen_prompts) == 2
    assert "photosynthesis" in seen_prompts[0]
    assert "cellular respiration" not in seen_prompts[0]
    assert "cellular respiration" in seen_prompts[1]
    assert "photosynthesis" not in seen_prompts[1]
