"""Deliver finalized lead payloads to configured CRM webhooks."""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.webhook_store import get_webhook_url

logger = logging.getLogger(__name__)


def deliver_leads_to_webhook(payload: dict[str, Any]) -> bool:
    """
    POST the finalized scrape result to the user's configured webhook.

    @param payload - Final result dict with leads, total, message
    @returns True when delivery succeeded, False when skipped or failed
    """
    webhook_url = get_webhook_url()
    if not webhook_url:
        logger.debug("No webhook URL configured; skipping delivery")
        return False

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "IntentEngine/3.0"},
            timeout=30,
        )
        response.raise_for_status()
        logger.info(
            "Webhook delivered %d leads to %s (status=%s)",
            payload.get("total", 0),
            webhook_url,
            response.status_code,
        )
        return True
    except requests.RequestException as exc:
        logger.error("Webhook delivery failed for %s: %s", webhook_url, exc)
        return False
