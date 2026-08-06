from pathlib import Path

from fastapi.testclient import TestClient

from learning_assistant.main import app
from learning_assistant.storage import SQLiteRepository

_TEST_PASSWORD = "Password123"


def _swap_repository(repository: SQLiteRepository) -> SQLiteRepository | None:
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository
    return previous_repository


def _restore_repository(previous_repository: SQLiteRepository | None) -> None:
    if previous_repository is None:
        delattr(app.state, "repository")
    else:
        app.state.repository = previous_repository


def test_signup_creates_account_and_logs_in(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        client = TestClient(app)
        response = client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
            follow_redirects=False,
        )
        home_response = client.get("/")
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert home_response.status_code == 200


def test_signup_rejects_duplicate_username(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        client = TestClient(app)
        client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
        second_response = client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert second_response.status_code == 400
    assert "already taken" in second_response.text.lower()


def test_signup_rejects_mismatched_passwords(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        client = TestClient(app)
        response = client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": "SomethingElse1",
            },
        )
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert response.status_code == 400


def test_login_with_correct_credentials_succeeds(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        client = TestClient(app)
        client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
        client.post("/logout")
        login_response = client.post(
            "/login",
            data={"username": "alice", "password": _TEST_PASSWORD},
            follow_redirects=False,
        )
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert login_response.status_code == 303
    assert login_response.headers["location"] == "/"


def test_login_with_wrong_password_fails(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        client = TestClient(app)
        client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
        client.post("/logout")
        login_response = client.post(
            "/login",
            data={"username": "alice", "password": "WrongPassword1"},
        )
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert login_response.status_code == 400


def test_logout_requires_login_again_to_access_home(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        client = TestClient(app)
        client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
        client.post("/logout")
        home_response = client.get("/", follow_redirects=False)
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert home_response.status_code == 303
    assert home_response.headers["location"].startswith("/login")


def test_user_cannot_access_another_users_study_set(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "auth.db")
    previous_repository = _swap_repository(repository)

    try:
        repository.save_question(
            source_pdf="alice-set.pdf",
            question_text="Question",
            options=["Answer"],
            correct_index=0,
        )

        client = TestClient(app)
        client.post(
            "/signup",
            data={
                "username": "alice",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
        alice = repository.get_user_by_username("alice")
        assert alice is not None
        repository.assign_set_owner("alice-set.pdf", alice.id)
        client.post("/logout")

        client.post(
            "/signup",
            data={
                "username": "bob",
                "password": _TEST_PASSWORD,
                "confirm_password": _TEST_PASSWORD,
            },
        )
        bob_response = client.get("/quiz/alice-set.pdf")
    finally:
        repository.close()
        _restore_repository(previous_repository)

    assert bob_response.status_code == 404
