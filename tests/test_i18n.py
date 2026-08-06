from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from learning_assistant.i18n import (
    _TRANSLATIONS,
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    translate,
)
from learning_assistant.main import app
from learning_assistant.storage import SQLiteRepository


def _set_repository(tmp_path: Path, name: str) -> SQLiteRepository:
    return SQLiteRepository(tmp_path / name)


def test_every_translation_key_has_all_supported_languages() -> None:
    for key, entry in _TRANSLATIONS.items():
        for language in SUPPORTED_LANGUAGES:
            assert entry.get(language), f"'{key}' is missing a '{language}' translation"


def test_translate_falls_back_to_the_key_when_unknown() -> None:
    assert translate(DEFAULT_LANGUAGE, "not_a_real_key") == "not_a_real_key"


def test_translate_formats_placeholders_per_language() -> None:
    assert (
        translate("en", "quiz_source_set", name="Chapter 1") == "Source set: Chapter 1"
    )
    assert translate("tr", "quiz_source_set", name="Bölüm 1") == "Kaynak set: Bölüm 1"


def test_home_page_defaults_to_english(tmp_path: Path) -> None:
    repository = _set_repository(tmp_path, "i18n-default.db")
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
    assert '<html lang="en">' in response.text
    assert "Learn from your PDFs" in response.text


def test_setting_language_persists_across_requests(tmp_path: Path) -> None:
    repository = _set_repository(tmp_path, "i18n-switch.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        client = TestClient(app)
        switch_response = client.post(
            "/settings/language",
            data={"language": "tr", "next": "/"},
            follow_redirects=False,
        )
        assert switch_response.status_code == 303
        assert switch_response.headers["location"] == "/"

        home_response = client.get("/")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert '<html lang="tr">' in home_response.text
    assert "tek seferde bir sınav ile" in home_response.text


def test_setting_an_unsupported_language_is_ignored(tmp_path: Path) -> None:
    repository = _set_repository(tmp_path, "i18n-invalid.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        client = TestClient(app)
        client.post(
            "/settings/language",
            data={"language": "fr", "next": "/"},
            follow_redirects=False,
        )
        home_response = client.get("/")
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert '<html lang="en">' in home_response.text


def test_setting_language_rejects_open_redirect_targets(tmp_path: Path) -> None:
    repository = _set_repository(tmp_path, "i18n-redirect.db")
    previous_repository = getattr(app.state, "repository", None)
    app.state.repository = repository

    try:
        client = TestClient(app)
        absolute_url_response = client.post(
            "/settings/language",
            data={"language": "tr", "next": "https://evil.example/pwn"},
            follow_redirects=False,
        )
        protocol_relative_response = client.post(
            "/settings/language",
            data={"language": "tr", "next": "//evil.example/pwn"},
            follow_redirects=False,
        )
    finally:
        repository.close()
        if previous_repository is None:
            delattr(app.state, "repository")
        else:
            app.state.repository = previous_repository

    assert absolute_url_response.headers["location"] == "/"
    assert protocol_relative_response.headers["location"] == "/"
