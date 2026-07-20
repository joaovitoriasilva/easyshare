"""Tests for the outgoing email service and verification-code delivery."""

from __future__ import annotations

import smtplib

import pytest
from app.services import email as email_module
from app.services.email import (
    EmailError,
    NullEmailSender,
    SmtpEmailSender,
    build_email_sender,
)


def test_null_sender_is_noop() -> None:
    # Must not raise; it only logs that email is disabled.
    NullEmailSender().send(to="x@example.com", subject="s", body="b")


def test_build_email_sender_selects_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "smtp_host", "")
    assert isinstance(build_email_sender(), NullEmailSender)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    assert isinstance(build_email_sender(), SmtpEmailSender)


def test_smtp_sender_wraps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> object:
        raise OSError("connect failed")

    monkeypatch.setattr(smtplib, "SMTP", _boom)
    sender = SmtpEmailSender(
        host="h",
        port=25,
        username="",
        password="",
        sender="from@example.test",
        use_tls=False,
        timeout=1,
    )
    with pytest.raises(EmailError):
        sender.send(to="to@example.test", subject="s", body="b")


def test_send_verification_code_swallows_delivery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Failing:
        def send(self, *, to: str, subject: str, body: str) -> None:
            raise EmailError("nope")

    monkeypatch.setattr(email_module, "email_sender", _Failing())
    # A delivery failure must never propagate to the caller (the route responds
    # uniformly and only logs).
    email_module.send_share_verification_code(
        "x@example.test", "123456", package_name="Docs"
    )
