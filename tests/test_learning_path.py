from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from learning_assistant.main import app
from learning_assistant.storage import SQLiteRepository


def _set_repository(tmp_path: Path, name: str) -> SQLiteRepository:
    repository = SQLiteRepository(tmp_path / name)
    repository.save_question(
        source_pdf="chapter-1.pdf",
        question_text="What is the capital of France?",
        options=["Berlin", "Madrid", "Paris", "Rome"],
        correct_index=2,
    )
    return repository


def test_learning_path_page_generates_once_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "learning-path.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    infer_calls = 0

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            nonlocal infer_calls
            infer_calls += 1
            return (
                '{"overview": "Learn European capitals.", '
                '"steps": [{"topic": "Geography basics", '
                '"summary": "Understand where France is.", '
                '"resources": [{"title": "World atlas", '
                '"url": "https://example.test/atlas", "description": "Reference map."}]}]}'
            )

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)

    try:
        client = TestClient(app)
        first_response = client.get("/learning-path/chapter-1.pdf")
        second_response = client.get("/learning-path/chapter-1.pdf")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert first_response.status_code == 200
    assert "Learn European capitals." in first_response.text
    assert "World atlas" in first_response.text
    assert second_response.status_code == 200
    assert "Learn European capitals." in second_response.text
    assert infer_calls == 1


def test_learning_path_page_shows_error_when_generation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "learning-path-error.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            return "not valid json"

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)

    try:
        response = TestClient(app).get("/learning-path/chapter-1.pdf")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 200
    assert "Could not generate a learning path" in response.text


def test_regenerate_learning_path_replaces_stored_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "learning-path-regen.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    responses = iter(
        [
            '{"overview": "First version.", "steps": []}',
            '{"overview": "Second version.", "steps": []}',
        ]
    )

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            return next(responses)

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)

    try:
        client = TestClient(app)
        first_response = client.get("/learning-path/chapter-1.pdf")
        regenerate_response = client.post(
            "/learning-path/chapter-1.pdf/regenerate", follow_redirects=False
        )
        second_response = client.get("/learning-path/chapter-1.pdf")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert "First version." in first_response.text
    assert regenerate_response.status_code == 303
    assert regenerate_response.headers["location"] == "/learning-path/chapter-1.pdf"
    assert "Second version." in second_response.text


def test_delete_set_removes_document_text_and_learning_path(tmp_path: Path) -> None:
    repository = _set_repository(tmp_path, "learning-path-delete.db")
    repository.save_document_text("chapter-1.pdf", "Some extracted text.")
    repository.save_learning_path("chapter-1.pdf", '{"overview": "x", "steps": []}')
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        TestClient(app).post("/sets/chapter-1.pdf/delete")
        remaining_text = repository.get_document_text("chapter-1.pdf")
        remaining_path = repository.get_learning_path("chapter-1.pdf")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert remaining_text is None
    assert remaining_path is None
