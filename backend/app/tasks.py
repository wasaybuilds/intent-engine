"""Celery tasks that run the lead scrape pipeline off the API request path."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.repository import save_leads_for_job, update_scrape_job_status
from app.scraper import LeadScraper, ScrapeConfig
from app.webhook_delivery import deliver_leads_to_webhook

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.run_scrape_job")
def run_scrape_job(self, niche: str, location: str) -> dict[str, Any]:
    """
    Execute discovery → LLM enrichment → email validation as a background job.

    Persists leads to PostgreSQL and delivers to webhook on completion.

    @param niche - Business niche
    @param location - Geographic area
    @returns Final scrape payload (leads, total, message)
    """
    task_id = self.request.id
    logger.info("Celery scrape started task_id=%s niche=%r location=%r", task_id, niche, location)

    db = SessionLocal()
    try:
        update_scrape_job_status(db, task_id, "STARTED")

        def on_progress(step: str, detail: str, percent: int, **extra: Any) -> None:
            """Publish pipeline progress into Celery meta for API polling."""
            self.update_state(
                state="PROGRESS",
                meta={
                    "step": step,
                    "detail": detail,
                    "percent": percent,
                    "companies_found": extra.get("companies_found", 0),
                    "companies_processed": extra.get("companies_processed", 0),
                },
            )

        on_progress("PENDING", "Job accepted, starting pipeline…", 5)

        scraper = LeadScraper(
            config=ScrapeConfig(max_companies=settings.max_companies),
            on_progress=on_progress,
        )
        raw_leads = asyncio.run(scraper.scrape(niche, location))

        verified_count = sum(1 for lead in raw_leads if lead.get("verified_email"))
        message = (
            f"Found {len(raw_leads)} decision maker(s), "
            f"{verified_count} with verified email(s)."
            if raw_leads
            else "No decision makers found. Try a broader niche or different location."
        )

        result = {
            "leads": raw_leads,
            "total": len(raw_leads),
            "message": message,
        }

        save_leads_for_job(db, task_id, raw_leads)
        update_scrape_job_status(db, task_id, "SUCCESS", message)

        on_progress("WEBHOOK", "Delivering leads to configured webhook…", 98)
        deliver_leads_to_webhook(result)

        logger.info("Celery scrape finished task_id=%s: %s", task_id, message)
        return result

    except Exception as exc:
        update_scrape_job_status(db, task_id, "FAILURE", str(exc))
        logger.exception("Celery scrape failed task_id=%s", task_id)
        raise RuntimeError(str(exc)) from exc
    finally:
        db.close()
