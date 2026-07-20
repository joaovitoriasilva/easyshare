"""Security helpers: password hashing, JWT tokens and share id generation."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import OctKey
from joserfc.jwt import JWTClaimsRegistry
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings
from app.core.utils import normalize_email

# Argon2id for password hashing: unlike bcrypt it has no 72-byte input limit and
# is memory-hard. pwdlib also replaces passlib, which is unmaintained and stops
# working on Python 3.14+ (the minimum this project targets).
_password_hash = PasswordHash((Argon2Hasher(),))

# Argon2id is deliberately memory- and CPU-hard, and password hashing runs on
# the request-handling threadpool (all routes are sync). Without a bound, a
# burst of logins/registrations could run many hashes at once — multiplying the
# memory-hard cost (risking OOM) and saturating every CPU core — which would
# stall unrelated requests sharing that threadpool. This bounded semaphore caps
# how many hashes run concurrently; excess auth requests queue briefly instead
# of degrading the whole instance.
_hash_semaphore = threading.BoundedSemaphore(settings.password_hash_concurrency)

# A throwaway hash computed once at import so the "user not found" login branch
# can perform the same Argon2 work as a real verify. Without it that branch
# returns far faster than a wrong-password verify, letting an attacker enumerate
# valid accounts by timing the response.
_DUMMY_HASH = _password_hash.hash(secrets.token_urlsafe(32))

# Marks a token as a restricted-share download credential rather than a user
# access token, so the two can never be used interchangeably.
_SHARE_ACCESS_SCOPE = "share-access"

# Marks a token as an owner download credential scoped to a single package, so a
# plain browser navigation can stream a download without an Authorization
# header (which would otherwise force the SPA to buffer large files in memory).
_DOWNLOAD_SCOPE = "download"
# Owner download tokens are consumed immediately by the browser, so they only
# need to outlive the round trip between issuing the token and navigating.
_DOWNLOAD_TOKEN_TTL = timedelta(minutes=5)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id (bounded concurrency)."""
    with _hash_semaphore:
        return _password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored Argon2 hash."""
    with _hash_semaphore:
        return _password_hash.verify(plain_password, hashed_password)


def dummy_verify() -> None:
    """Run a throwaway verify to equalise login timing for unknown users.

    Called on the "user not found" branch of login so its latency matches the
    "found, wrong password" branch, closing a username-enumeration side channel.
    Always performs a full Argon2 verify and discards the (always ``False``)
    result.
    """
    with _hash_semaphore:
        _password_hash.verify(secrets.token_urlsafe(32), _DUMMY_HASH)


# JWT signing key and claims validator, built once at import (mirroring the
# import-time construction of the password hasher above). joserfc keeps the two
# concerns separate: ``jwt.decode`` verifies the signature and restricts the
# accepted algorithm, while ``JWTClaimsRegistry.validate`` enforces the ``exp``
# claim. The key material is the shared application secret.
_signing_key = OctKey.import_key(settings.secret_key)
_claims_registry = JWTClaimsRegistry()


def _encode(claims: dict[str, Any]) -> str:
    """Sign ``claims`` into a compact JWS (``exp`` datetimes become timestamps)."""
    return jwt.encode(
        {"alg": settings.algorithm},
        claims,
        _signing_key,
        algorithms=[settings.algorithm],
    )


def _decode(token: str) -> dict[str, Any] | None:
    """Return a valid, unexpired token's claims, or ``None`` if it is invalid.

    ``algorithms`` pins the single accepted algorithm so a token signed with a
    different one (an algorithm-substitution attack) is rejected; the claims
    registry then rejects an expired token. Any failure maps to ``None`` so
    every caller treats an unusable token as simply unauthenticated.
    """
    try:
        decoded = jwt.decode(token, _signing_key, algorithms=[settings.algorithm])
        _claims_registry.validate(decoded.claims)
    except (JoseError, ValueError):
        return None
    return decoded.claims


def create_access_token(
    subject: str | int, expires_delta: timedelta | None = None
) -> str:
    """Create a signed JWT access token for ``subject`` (the user id)."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    return _encode({"sub": str(subject), "exp": expire})


def decode_access_token(token: str) -> str | None:
    """Return the subject of a valid token, or ``None`` if invalid/expired."""
    claims = _decode(token)
    if claims is None:
        return None
    # A user access token carries no scope; reject anything scoped (e.g. a
    # share-access download token) so the two token types can never be used
    # interchangeably even though they are signed with the same key.
    if claims.get("scope") is not None:
        return None
    subject = claims.get("sub")
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
    return _encode(
        {
            "scope": _SHARE_ACCESS_SCOPE,
            "sub": share_token,
            "email": email,
            "exp": expire,
        }
    )


def decode_share_access_token(token: str, share_token: str) -> str | None:
    """Return the authorised email carried by a valid share-access token.

    Returns ``None`` unless the token is correctly signed, unexpired, carries the
    share-access scope and was issued for ``share_token``.
    """
    claims = _decode(token)
    if claims is None:
        return None
    if claims.get("scope") != _SHARE_ACCESS_SCOPE:
        return None
    if claims.get("sub") != share_token:
        return None
    email = claims.get("email")
    if not isinstance(email, str):
        return None
    return email


def create_download_token(
    user_id: int, package_id: int, expires_delta: timedelta | None = None
) -> str:
    """Create a short-lived token letting ``user_id`` download ``package_id``.

    Lets the browser fetch a file or archive with a plain navigation (no
    Authorization header), so large downloads stream to disk instead of being
    buffered in memory by the SPA.
    """
    expire = datetime.now(UTC) + (expires_delta or _DOWNLOAD_TOKEN_TTL)
    return _encode(
        {
            "scope": _DOWNLOAD_SCOPE,
            "sub": str(user_id),
            "pkg": package_id,
            "exp": expire,
        }
    )


def decode_download_token(token: str) -> tuple[int, int] | None:
    """Return ``(user_id, package_id)`` for a valid download token, else ``None``."""
    claims = _decode(token)
    if claims is None:
        return None
    if claims.get("scope") != _DOWNLOAD_SCOPE:
        return None
    subject = claims.get("sub")
    package_id = claims.get("pkg")
    if subject is None or not isinstance(package_id, int):
        return None
    try:
        return int(subject), package_id
    except (TypeError, ValueError):
        return None


def generate_share_token() -> str:
    """Generate a cryptographically secure, URL-safe share identifier."""
    return secrets.token_urlsafe(24)


def generate_verification_code() -> str:
    """Return a random 6-digit numeric one-time code (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_verification_code(share_id: int, email: str, code: str) -> str:
    """Return a keyed hash binding a one-time ``code`` to a share and email.

    HMAC-SHA256 keyed with the app secret so the stored value is useless without
    the server key (a database leak alone cannot recover codes), and binding the
    share id and email so a hash can never be replayed against a different share
    or recipient. The plaintext code is never stored.
    """
    message = f"{share_id}:{normalize_email(email)}:{code}".encode()
    return hmac.new(
        settings.secret_key.encode(), message, hashlib.sha256
    ).hexdigest()


def verify_verification_code(
    share_id: int, email: str, code: str, expected_hash: str
) -> bool:
    """Constant-time check of a submitted code against its stored hash."""
    candidate = hash_verification_code(share_id, email, code)
    return hmac.compare_digest(candidate, expected_hash)
