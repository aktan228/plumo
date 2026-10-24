"""Transactional account mail via Resend. Tokens are never written to logs or returned by the API."""

import asyncio
import os
from dataclasses import dataclass
from html import escape
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.config import Settings
from app.domain.errors import NotConfigured, ProviderUnavailable


@dataclass(frozen=True)
class AuthEmail:
    id: UUID
    recipient: str
    purpose: str
    link: str
    locale: str


def email_content(mail: AuthEmail) -> tuple[str, str, str]:
    en = mail.locale == "en"
    if mail.purpose == "verify":
        title = "Verify your Plumo email" if en else "Подтвердите почту Plumo"
        action = "Verify email" if en else "Подтвердить почту"
        description = (
            "Confirm your email to open your workspace. This link expires in 24 hours."
            if en
            else "Подтвердите почту, чтобы открыть кабинет. Ссылка действует 24 часа."
        )
    else:
        title = "Reset your Plumo password" if en else "Сброс пароля Plumo"
        action = "Set a new password" if en else "Задать новый пароль"
        description = (
            "This password reset link expires in 30 minutes." if en else "Ссылка для сброса пароля действует 30 минут."
        )
    ignore = (
        "If you did not request this email, ignore it. Your password has not changed."
        if en
        else "Если вы не запрашивали это письмо, проигнорируйте его. Ваш пароль не изменён."
    )
    text = f"{title}\n\n{description}\n\n{action}: {mail.link}\n\n{ignore}"
    html = f'<html><body style="font-family:Arial,sans-serif;color:#151515;max-width:520px;margin:40px auto;padding:24px"><p style="font-weight:bold">Plumo</p><h1>{title}</h1><p>{description}</p><p style="margin:32px 0"><a href="{escape(mail.link, quote=True)}" style="background:#151515;color:white;padding:14px 20px;border-radius:12px;text-decoration:none">{action}</a></p><p style="color:#73737d">{ignore}</p></body></html>'
    return title, text, html


class ResendAuthMailer:
    def __init__(self, settings: Settings, *, transport=None):
        self.settings = settings
        self.transport = transport

    def check_config(self):
        parts = urlsplit(self.settings.auth_public_url)
        local = self.settings.is_development and parts.hostname in ("localhost", "127.0.0.1") and parts.scheme == "http"
        if (
            (not local and parts.scheme != "https")
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in ("", "/")
        ):
            raise NotConfigured("Set AUTH_PUBLIC_URL to the frontend HTTPS origin.")
        if not os.getenv("RESEND_API_KEY", "").strip() or not self.settings.auth_email_from.strip():
            raise NotConfigured("Account mail needs RESEND_API_KEY and AUTH_EMAIL_FROM on the backend.")

    async def send(self, mail: AuthEmail):
        self.check_config()
        subject, text, html = email_content(mail)
        headers = {
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Idempotency-Key": f"account-mail/{mail.id}",
        }
        payload = {
            "from": self.settings.auth_email_from,
            "to": [mail.recipient],
            "subject": subject,
            "text": text,
            "html": html,
        }
        async with httpx.AsyncClient(timeout=10, transport=self.transport) as client:
            for attempt in range(2):
                try:
                    response = await client.post("https://api.resend.com/emails", headers=headers, json=payload)
                    if response.is_success:
                        return
                    retry = response.status_code == 429 or response.status_code >= 500
                except httpx.HTTPError:
                    retry = True
                if not retry or attempt:
                    break
                await asyncio.sleep(0.2)
        # No provider body, email, token or secret in this error.
        raise ProviderUnavailable("Account email could not be delivered; request another link later.")
