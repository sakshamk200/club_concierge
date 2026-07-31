"""Password hashing and session-token signing for first-party accounts.

Passwords are stored only as salted PBKDF2-SHA256 digests (stdlib, no external
dependency). Session tokens are stateless HMAC-signed values — no server-side
session table — verified on every authenticated request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 200_000
_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # one week


def hash_password(password: str) -> str:
    """Return a salted PBKDF2-SHA256 hash string for storage."""

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a candidate password against a stored hash."""

    try:
        scheme, iters_text, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        iterations = int(iters_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        logger.error("Malformed password hash encountered")
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(candidate, expected)


def _signing_key(settings: Settings) -> bytes:
    return settings.auth_secret.encode("utf-8")


def issue_token(user_id: str, settings: Settings | None = None) -> str:
    """Create a signed session token embedding the user id and expiry."""

    settings = settings or get_settings()
    expires = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{user_id}.{expires}".encode("utf-8")
    signature = hmac.new(_signing_key(settings), payload, hashlib.sha256).digest()
    raw = payload + b"." + base64.urlsafe_b64encode(signature)
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_token(token: str, settings: Settings | None = None) -> str | None:
    """Return the user id for a valid, unexpired token; None otherwise."""

    settings = settings or get_settings()
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload, sig_b64 = raw.rsplit(b".", 1)
        user_id_bytes, expires_bytes = payload.rsplit(b".", 1)
        expected = hmac.new(
            _signing_key(settings), payload, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(base64.urlsafe_b64decode(sig_b64), expected):
            return None
        if int(expires_bytes) < time.time():
            return None
        return user_id_bytes.decode("utf-8")
    except Exception:
        return None
