#!/usr/bin/env python3
"""community/discord.py — Discord webhook & REST API client adapter (S4.2).

Handles formatting of pod weekly check-ins into structured Discord embed payloads,
posting to Discord webhook endpoints or bot channel message endpoints, and graceful error handling.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DISCORD_TIMEOUT_S = 10


def discord_api_base() -> str:
    return os.environ.get("KEEL_DISCORD_API_URL", "https://discord.com/api/v10")


def discord_bot_token() -> str | None:
    return os.environ.get("KEEL_DISCORD_BOT_TOKEN") or None


def discord_webhook_url() -> str | None:
    return os.environ.get("KEEL_DISCORD_WEBHOOK_URL") or None


def format_pod_post_embed(
    student_name: str,
    pod_name: str,
    cohort_week: str,
    week_number: int,
    shipped_text: str,
    broke_text: str,
    next_text: str,
) -> dict[str, Any]:
    """Format the mandatory 3-pillar accountability post into a Discord webhook/message payload."""
    return {
        "content": f"**Weekly Accountability Check-In: {student_name} (Week {week_number})**",
        "embeds": [
            {
                "title": f"Pod Check-In — {pod_name} ({cohort_week})",
                "color": 0x10B981,  # emerald green
                "fields": [
                    {
                        "name": "1. What Shipped",
                        "value": shipped_text.strip() or "*Nothing reported*",
                        "inline": False,
                    },
                    {
                        "name": "2. What Broke",
                        "value": broke_text.strip() or "*Nothing reported*",
                        "inline": False,
                    },
                    {
                        "name": "3. What's Next",
                        "value": next_text.strip() or "*Nothing reported*",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": f"Keel Academy Pod Accountability • Week {week_number}",
                },
            }
        ],
    }


def relay_pod_post_to_discord(
    student_name: str,
    pod_name: str,
    cohort_week: str,
    week_number: int,
    shipped_text: str,
    broke_text: str,
    next_text: str,
    discord_channel_id: str | None = None,
) -> str | None:
    """Relay a weekly pod post to Discord webhook or channel API.
    
    Returns the Discord message ID on success, or None if Discord is not configured / call failed.
    """
    payload = format_pod_post_embed(
        student_name=student_name,
        pod_name=pod_name,
        cohort_week=cohort_week,
        week_number=week_number,
        shipped_text=shipped_text,
        broke_text=broke_text,
        next_text=next_text,
    )

    webhook_url = discord_webhook_url()
    bot_token = discord_bot_token()
    base_api = discord_api_base()

    url: str | None = None
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if webhook_url:
        url = webhook_url
    elif discord_channel_id and bot_token:
        url = f"{base_api.rstrip('/')}/channels/{discord_channel_id}/messages"
        headers["Authorization"] = f"Bot {bot_token}"
    elif os.environ.get("KEEL_DISCORD_API_URL"):
        # Testing fallback against fake discord when webhook url isn't set explicitly
        url = f"{base_api.rstrip('/')}/channels/{discord_channel_id or 'default'}/messages"
        if bot_token:
            headers["Authorization"] = f"Bot {bot_token}"

    if not url:
        # Discord integration not wired in environment
        return None

    raw_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=raw_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=DISCORD_TIMEOUT_S) as resp:
            resp_body = resp.read().decode("utf-8")
            if resp_body:
                doc = json.loads(resp_body)
                return str(doc.get("id", "")) or "disc_relayed"
            return "disc_relayed"
    except Exception as exc:
        sys.stderr.write(f"discord relay warning: failed to post to discord: {exc}\n")
        return None
