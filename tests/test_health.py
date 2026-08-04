from pathlib import Path

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
