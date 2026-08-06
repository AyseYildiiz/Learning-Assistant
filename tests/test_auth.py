from learning_assistant.auth import (
    hash_password,
    validate_password,
    validate_username,
    verify_password,
)


def test_validate_username_accepts_valid_usernames() -> None:
    assert validate_username("alice") is None
    assert validate_username("alice_bob-2.0") is None


def test_validate_username_rejects_too_short_or_invalid_characters() -> None:
    assert validate_username("ab") == "error_invalid_username"
    assert validate_username("has spaces") == "error_invalid_username"
    assert validate_username("a" * 33) == "error_invalid_username"


def test_validate_password_requires_minimum_length() -> None:
    assert validate_password("short1") == "error_password_too_short"


def test_validate_password_requires_letter_and_digit() -> None:
    assert validate_password("alllettersnodigits") == (
        "error_password_needs_letter_and_digit"
    )
    assert validate_password("12345678") == "error_password_needs_letter_and_digit"


def test_validate_password_accepts_valid_password() -> None:
    assert validate_password("Password123") is None


def test_hash_password_and_verify_password_round_trip() -> None:
    password_hash, salt = hash_password("Password123")

    assert verify_password("Password123", password_hash, salt)
    assert not verify_password("WrongPassword1", password_hash, salt)


def test_hash_password_uses_a_random_salt_each_time() -> None:
    first_hash, first_salt = hash_password("Password123")
    second_hash, second_salt = hash_password("Password123")

    assert first_salt != second_salt
    assert first_hash != second_hash
