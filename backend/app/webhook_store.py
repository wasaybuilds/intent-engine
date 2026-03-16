"""Persist and retrieve the configured CRM webhook URL via Redis."""

from __future__ import annotations

import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

WEBHOOK_REDIS_KEY = "intent_engine:webhook_url"


def _client() -> redis.Redis:
    """Return a Redis client using the shared broker URL."""
    return redis.from_url(settings.redis_url, decode_responses=True)


def get_webhook_url() -> str | None:
    """
    Read the configured webhook URL.

    @returns URL string or None if not configured
    """
    try:
        url = _client().get(WEBHOOK_REDIS_KEY)
        return url if url else None
    except redis.RedisError as exc:
        logger.warning("Failed to read webhook URL from Redis: %s", exc)
        return None


def set_webhook_url(url: str) -> None:
    """
    Save the CRM / sequencer webhook URL.

    @param url - HTTPS endpoint to POST enriched leads
    """
    _client().set(WEBHOOK_REDIS_KEY, url.strip())


def clear_webhook_url() -> None:
    """Remove the stored webhook URL."""
    _client().delete(WEBHOOK_REDIS_KEY)
