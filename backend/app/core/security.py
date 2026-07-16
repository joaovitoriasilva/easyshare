"""Security helpers: password hashing, JWT tokens and share id generation."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

# Argon2id for password hashing: unlike bcrypt it has no 72-byte input limit and
# is memory-hard. pwdlib also replaces passlib, which is unmaintained and stops
# working on Python 3.13+ (the minimum this project targets).
_password_hash = PasswordHash((Argon2Hasher(),))

# A throwaway hash computed once at import so the "user not found" login branch
# can perform the same Argon2 work as a real verify. Without it that branch
# returns far faster than a wrong-password verify, letting an attacker enumerate
# valid accounts by timing the response.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(32))

# Marks a token as a restricted-share download credential rather than a user
# access token, so the two can never be used interchangeably.
_SHARE_ACCESS_SCOPE = "share-access"


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored Argon2 hash."""
    return _password_hash.verify(plain_password, hashed_password)


def dummy_verify() -> None:
    """Run a throwaway verify to equalise login timing for unknown users.

    Called on the "user not found" branch of login so its latency matches the
    "found, wrong password" branch, closing a username-enumeration side channel.
    Always performs a full Argon2 verify and discards the (always ``False``)
    result.
    """
    _password_hash.verify(secrets.token_urlsafe(32), _DUMMY_HASH)


def create_access_token(
    subject: str | int, expires_delta: timedelta | None = None
) -> str:
    """Create a signed JWT access token for ``subject`` (the user id)."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the subject of a valid token, or ``None`` if invalid/expired."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        return None
    subject = payload.get("sub")
    if subject is None:
        return None
    return str(subject)


def create_share_access_token(
    share_token: str, email: str, expires_delta: timedelta | None = None
) -> str:
    """Create a short-lived token proving ``email`` may access ``share_token``.

    Issued by the restricted-share ``/access`` endpoint so download requests can
    carry an opaque, expiring credential instead of the recipient's email
    address, which would otherwise leak via URLs, access logs and ``Referer``
    headers.
    """
    expire = datetime.now(UTC) + (
        expires_delta
        or timedelta(minutes=settings.share_access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "scope": _SHARE_ACCESS_SCOPE,
        "sub": share_token,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_share_access_token(token: str, share_token: str) -> str | None:
    """Return the authorised email carried by a valid share-access token.

    Returns ``None`` unless the token is correctly signed, unexpired, carries the
    share-access scope and was issued for ``share_token``.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        return None
    if payload.get("scope") != _SHARE_ACCESS_SCOPE:
        return None
    if payload.get("sub") != share_token:
        return None
    email = payload.get("email")
    if not isinstance(email, str):
        return None
    return email


def generate_share_token() -> str:
    """Generate a cryptographically secure, URL-safe share identifier."""
    return secrets.token_urlsafe(24)
