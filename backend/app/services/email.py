"""Outgoing email delivery for restricted-share verification codes.

The active sender is chosen from configuration by :func:`build_email_sender`:
when ``smtp_host`` is set, mail is delivered over SMTP; otherwise a no-op sender
is used and the caller is expected to have already decided (via
``settings.email_verification_enabled``) not to require verification at all.

Domain code depends only on the :class:`EmailSender` interface, so the transport
can be swapped (or captured in tests) without touching the routes.
"""

from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("easyshare.email")


class EmailError(Exception):
    """Raised when an email could not be delivered."""


class EmailSender(ABC):
    """Interface every email transport implements."""

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> None:
        """Deliver a plain-text email.

        Raises:
            EmailError: If the message could not be delivered.
        """


class SmtpEmailSender(EmailSender):
    """Delivers mail through an SMTP server (STARTTLS by default)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        use_tls: bool,
        timeout: int,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._use_tls = use_tls
        self._timeout = timeout

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            # Never surface the raw SMTP error to the caller/recipient; it can
            # leak server details. The route logs and responds uniformly.
            raise EmailError("Failed to send email") from exc


class NullEmailSender(EmailSender):
    """No-op sender used when no SMTP host is configured."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        logger.warning(
            "email.disabled_send_skipped",
            extra={"subject": subject},
        )


def build_email_sender() -> EmailSender:
    """Build the email sender selected by configuration."""
    if not settings.email_verification_enabled:
        return NullEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host.strip(),
        port=settings.smtp_port,
        username=settings.smtp_username.strip(),
        password=settings.smtp_password,
        sender=settings.smtp_sender,
        use_tls=settings.smtp_use_tls,
        timeout=settings.smtp_timeout,
    )


email_sender: EmailSender = build_email_sender()


def send_share_verification_code(to: str, code: str, *, package_name: str) -> None:
    """Email a one-time verification ``code`` for a restricted share.

    Delivery failures are logged and swallowed so the caller can respond
    uniformly (never revealing whether an address is on the allow-list).
    """
    subject = f"Your access code for “{package_name}”"
    body = (
        "Hello,\n\n"
        f"Use this code to access the shared package “{package_name}”:\n\n"
        f"    {code}\n\n"
        "The code expires shortly. If you did not request access, you can "
        "ignore this email.\n"
    )
    try:
        email_sender.send(to=to, subject=subject, body=body)
    except EmailError:
        logger.exception("email.verification_send_failed")
