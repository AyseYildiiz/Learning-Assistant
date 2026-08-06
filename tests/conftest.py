from fastapi.testclient import TestClient

from learning_assistant.storage import SQLiteRepository

_TEST_PASSWORD = "Password123"


def authenticate(
    client: TestClient,
    repository: SQLiteRepository,
    *owned_source_pdfs: str,
    username: str = "studyflow-tester",
) -> int:
    """Sign up (and log in) a test user, assigning ownership of any given sets."""
    response = client.post(
        "/signup",
        data={
            "username": username,
            "password": _TEST_PASSWORD,
            "confirm_password": _TEST_PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text

    user = repository.get_user_by_username(username)
    assert user is not None
    for source_pdf in owned_source_pdfs:
        repository.assign_set_owner(source_pdf, user.id)

    return user.id
