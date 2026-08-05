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


def test_chat_returns_fragment_with_assistant_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "chat.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            return "Paris is the capital of France."

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)

    try:
        client = TestClient(app)
        response = client.post(
            "/chat/chapter-1.pdf", data={"message": "What is the capital?"}
        )
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 200
    assert "Paris is the capital of France." in response.text


def test_chat_history_is_included_in_the_next_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "chat-history.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    seen_prompts: list[str] = []

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            seen_prompts.append(prompt)
            return f"reply-{len(seen_prompts)}"

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)

    try:
        client = TestClient(app)
        client.post("/chat/chapter-1.pdf", data={"message": "First question"})
        client.post("/chat/chapter-1.pdf", data={"message": "Second question"})
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert len(seen_prompts) == 2
    assert "First question" in seen_prompts[1]
    assert "reply-1" in seen_prompts[1]


def test_chat_rejects_empty_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "chat-empty.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        client = TestClient(app)
        response = client.post("/chat/chapter-1.pdf", data={"message": "   "})
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 422


def test_chat_returns_404_for_unknown_pdf(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "chat-missing.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        client = TestClient(app)
        response = client.post("/chat/missing.pdf", data={"message": "Hello?"})
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert response.status_code == 404


def test_chat_history_survives_a_page_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _set_repository(tmp_path, "chat-reload.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    class FakeGateway:
        def close(self) -> None:
            return None

        def infer(self, prompt: str, model: str | None = None) -> str:
            return "Paris is the capital of France."

    monkeypatch.setattr("learning_assistant.web.KSGatewayClient", FakeGateway)

    try:
        client = TestClient(app)
        client.post("/chat/chapter-1.pdf", data={"message": "What is the capital?"})
        quiz_response = client.get("/quiz/chapter-1.pdf")
        flashcards_response = client.get("/flashcards/chapter-1.pdf")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert "What is the capital?" in quiz_response.text
    assert "Paris is the capital of France." in quiz_response.text
    assert "What is the capital?" in flashcards_response.text
    assert "Paris is the capital of France." in flashcards_response.text
