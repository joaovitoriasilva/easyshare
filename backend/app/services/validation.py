"""Filename security validation backed by :mod:`safeuploads`.

EasyShare accepts arbitrary file types, so the high-level, allow-list based
``FileValidator.validate_*`` helpers (image/zip/activity/gzip) do not apply.
Instead we reuse safeuploads' type-agnostic filename validators to normalise
filenames and reject dangerous ones (path traversal, Unicode obfuscation,
Windows reserved names and blocked executable/script extensions) before a file
is persisted. Rejections raise :class:`safeuploads.FileValidationError`, which
is translated into an HTTP 400 by the application exception handler.
"""

from __future__ import annotations

import os
import time

from safeuploads import (
    ErrorCode,
    ExtensionSecurityValidator,
    FilenameSecurityError,
    FileSecurityConfig,
    UnicodeSecurityValidator,
    WindowsSecurityValidator,
)

_config = FileSecurityConfig()
_unicode_validator = UnicodeSecurityValidator(_config)
_windows_validator = WindowsSecurityValidator(_config)
_extension_validator = ExtensionSecurityValidator(_config)

# Characters that are unsafe in a stored filename or an HTTP
# ``Content-Disposition`` header value.
_DANGEROUS_CHARS = '<>:"/\\|?*\x00'
_MAX_STEM_LENGTH = 100


def sanitize_upload_filename(filename: str | None) -> str:
    """Return a hardened, safe-to-store filename.

    The filename is Unicode-normalised, stripped of path and control
    characters, and checked against Windows reserved names and a blocklist of
    dangerous extensions.

    Raises:
        FileValidationError: If the filename is empty or fails any of the
            Unicode, Windows reserved name or blocked extension checks.
    """
    if not filename:
        raise FilenameSecurityError(
            "Filename is required", error_code=ErrorCode.FILENAME_EMPTY
        )

    # Normalise Unicode and reject obfuscation attacks first.
    name = _unicode_validator.validate_unicode_security(filename)

    # Strip path components and control/dangerous characters.
    name = os.path.basename(name)
    name = "".join(char for char in name if ord(char) >= 32 and char != "\x7f")
    for char in _DANGEROUS_CHARS:
        name = name.replace(char, "_")

    # Reject Windows reserved device names and dangerous extensions.
    _windows_validator.validate_windows_reserved_names(name)
    _extension_validator.validate_extensions(name)

    # Bound the length while preserving the extension.
    stem, ext = os.path.splitext(name)
    if len(stem) > _MAX_STEM_LENGTH:
        name = stem[:_MAX_STEM_LENGTH] + ext
        stem = stem[:_MAX_STEM_LENGTH]
    if not stem or not stem.strip():
        name = f"file_{int(time.time())}{ext}"

    # Re-check reserved names after truncation/renaming.
    _windows_validator.validate_windows_reserved_names(name)
    return name
