"""Celery application wired to Redis as broker and result backend."""

from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "lead_scraper",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Keep completed results long enough for the frontend to poll
    result_expires=3600,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
