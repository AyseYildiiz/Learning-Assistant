"""Username/password hashing and validation helpers for user accounts."""

from __future__ import annotations

import hashlib
import re
import secrets

_PBKDF2_ITERATIONS = 600_000
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_MIN_PASSWORD_LENGTH = 8


def validate_username(username: str) -> str | None:
    """Return a translation key describing the problem, or None if valid."""
    if not _USERNAME_PATTERN.fullmatch(username):
        return "error_invalid_username"
    return None


def validate_password(password: str) -> str | None:
    """Return a translation key describing the problem, or None if valid."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        return "error_password_too_short"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "error_password_needs_letter_and_digit"
    return None


def hash_password(password: str) -> tuple[str, str]:
    """Return (password_hash, salt), both hex-encoded."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return secrets.compare_digest(digest.hex(), password_hash)
