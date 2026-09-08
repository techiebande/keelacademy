#!/usr/bin/env python3
"""community/email_transport.py — Email transport adapter for digest delivery (S4.3).

Supports:
- HTTP API client to fake_email server or production transactional email API (e.g. Resend / Postmark / SendGrid).
- SMTP fallback (if configured).
- Graceful error handling and delivery verification.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

EMAIL_TIMEOUT_S = 10


def email_api_url() -> str | None:
    """Returns the HTTP API URL for email dispatch (e.g. fake email server or transactional API)."""
    return os.environ.get("KEEL_EMAIL_API_URL") or os.environ.get("KEEL_FAKE_EMAIL_URL") or None


def smtp_config() -> dict[str, Any] | None:
    """Returns SMTP host/port config if environment is set."""
    host = os.environ.get("KEEL_SMTP_HOST")
    if not host:
        return None
    port = int(os.environ.get("KEEL_SMTP_PORT", "587"))
    user = os.environ.get("KEEL_SMTP_USER", "")
    password = os.environ.get("KEEL_SMTP_PASSWORD", "")
    return {"host": host, "port": port, "user": user, "password": password}


def deliver_email(
    to_email: str,
    subject: str,
    text_content: str,
    html_content: str,
    from_email: str = "Keel Academy <dispatch@keel.academy>",
) -> dict[str, Any]:
    """Deliver an email via HTTP API or SMTP transport.
    
    Returns a dict with {"ok": True, "delivery_id": ..., "transport": ...} or raises on fatal errors.
    """
    if not to_email or "@" not in to_email:
        raise ValueError("invalid_recipient_email")

    api_url = email_api_url()
    if api_url:
        target_url = f"{api_url.rstrip('/')}/api/v1/send" if not api_url.endswith("/send") else api_url
        payload = {
            "to": to_email,
            "from": from_email,
            "subject": subject,
            "text": text_content,
            "html": html_content,
        }
        raw_body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            target_url,
            data=raw_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=EMAIL_TIMEOUT_S) as resp:
                resp_body = resp.read().decode("utf-8")
                doc = json.loads(resp_body) if resp_body else {}
                delivery_id = doc.get("id") or doc.get("email_id") or "api_delivered"
                return {
                    "ok": True,
                    "delivery_id": str(delivery_id),
                    "transport": "http_api",
                    "recipient": to_email,
                }
        except Exception as exc:
            sys.stderr.write(f"email_transport: HTTP API delivery failed: {exc}\n")
            raise RuntimeError(f"email_delivery_failed: {exc}") from exc

    smtp_cfg = smtp_config()
    if smtp_cfg:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=EMAIL_TIMEOUT_S) as server:
                if smtp_cfg["user"] and smtp_cfg["password"]:
                    server.starttls()
                    server.login(smtp_cfg["user"], smtp_cfg["password"])
                server.sendmail(from_email, [to_email], msg.as_string())
            return {
                "ok": True,
                "delivery_id": "smtp_sent",
                "transport": "smtp",
                "recipient": to_email,
            }
        except Exception as exc:
            sys.stderr.write(f"email_transport: SMTP delivery failed: {exc}\n")
            raise RuntimeError(f"email_delivery_failed: {exc}") from exc

    # If neither API URL nor SMTP configured, fallback to stdout recording
    sys.stderr.write(f"email_transport: Warning - no email transport configured; simulated send to {to_email}\n")
    return {
        "ok": True,
        "delivery_id": "simulated_local",
        "transport": "simulated",
        "recipient": to_email,
    }
