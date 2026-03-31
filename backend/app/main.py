"""FastAPI application entry point for the B2B lead scraper."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from celery.result import AsyncResult
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.celery_app import celery_app
from app.config import settings
from app.db import User, get_db, init_db
from app.models import (
    ScrapeHistoryResponse,
    ScrapeJobDetailResponse,
    ScrapeJobSummary,
    ScrapeRequest,
    ScrapeResponse,
    TaskProgress,
    TaskStatusResponse,
    TaskSubmitResponse,
    WebhookConfigureRequest,
    WebhookConfigureResponse,
    WebhookStatusResponse,
)
from app.repository import (
    create_scrape_job,
    get_scrape_job_by_task_id,
    get_scrape_job_for_user,
    get_user_scrape_jobs,
)
from app.tasks import run_scrape_job
from app.webhook_store import get_webhook_url, set_webhook_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize PostgreSQL tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="B2B Lead Scraper API",
    description=(
        "Intent-driven lead engine with Clerk auth, PostgreSQL history, "
        "Celery jobs, and LLM enrichment."
    ),
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe for container and dev tooling."""
    return {"status": "ok"}


@app.post("/api/scrape", response_model=TaskSubmitResponse)
async def scrape_leads(
    payload: ScrapeRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TaskSubmitResponse:
    """
    Enqueue a scrape job for the authenticated user.

    @param payload - niche and location search parameters
    @param user - Verified Clerk user
    @param db - Database session
    @returns task_id with PENDING status
    """
    niche = payload.niche.strip()
    location = payload.location.strip()

    if not niche or not location:
        raise HTTPException(status_code=422, detail="Both niche and location are required.")

    task = run_scrape_job.delay(niche, location)
    create_scrape_job(db, user, task.id, niche, location)

    logger.info(
        "Enqueued scrape task_id=%s user_id=%s niche=%r location=%r",
        task.id,
        user.id,
        niche,
        location,
    )

    return TaskSubmitResponse(task_id=task.id, status="PENDING")


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TaskStatusResponse:
    """
    Poll Celery for scrape progress. User must own the job.

    @param task_id - ID returned by POST /api/scrape
    @returns Current status, progress, and result when complete
    """
    job = get_scrape_job_by_task_id(db, user.id, task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found.")

    result = AsyncResult(task_id, app=celery_app)
    status = result.status

    progress: TaskProgress | None = None
    scrape_result: ScrapeResponse | None = None
    error: str | None = None

    meta = _safe_meta(result)

    if status in ("PENDING", "STARTED", "PROGRESS", "RETRY"):
        progress = TaskProgress(
            step=str(meta.get("step", status)),
            detail=str(meta.get("detail", "Waiting for worker…" if status == "PENDING" else "")),
            percent=int(meta.get("percent", 0) or 0),
            companies_found=int(meta.get("companies_found", 0) or 0),
            companies_processed=int(meta.get("companies_processed", 0) or 0),
        )

    if status == "SUCCESS":
        payload = result.result or {}
        scrape_result = ScrapeResponse(
            leads=payload.get("leads", []),
            total=payload.get("total", 0),
            message=payload.get("message", ""),
        )
        progress = TaskProgress(
            step="COMPLETE",
            detail=scrape_result.message,
            percent=100,
            companies_processed=scrape_result.total,
        )

    if status == "FAILURE":
        if isinstance(result.result, Exception):
            error = str(result.result)
        elif isinstance(meta.get("exc_message"), str):
            error = meta["exc_message"]
        else:
            error = str(result.result or meta.get("detail") or "Task failed")
        progress = TaskProgress(step="FAILED", detail=error, percent=0)

    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        progress=progress,
        result=scrape_result,
        error=error,
    )


@app.get("/api/history", response_model=ScrapeHistoryResponse)
async def get_scrape_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ScrapeHistoryResponse:
    """
    List past scrape jobs for the authenticated user.

    @returns Job summaries ordered newest first
    """
    jobs = get_user_scrape_jobs(db, user.id)
    summaries = [
        ScrapeJobSummary(
            id=job.id,
            task_id=job.task_id,
            status=job.status,
            niche=job.niche,
            location=job.location,
            message=job.message,
            lead_count=len(job.leads),
            created_at=job.created_at.isoformat(),
        )
        for job in jobs
    ]
    return ScrapeHistoryResponse(jobs=summaries, total=len(summaries))


@app.get("/api/history/{job_id}", response_model=ScrapeJobDetailResponse)
async def get_scrape_job_detail(
    job_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ScrapeJobDetailResponse:
    """
    Fetch a historical scrape job with all persisted leads.

    @param job_id - ScrapeJob primary key
    @returns Job metadata and lead rows for CSV re-download
    """
    job = get_scrape_job_for_user(db, user.id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found.")

    return ScrapeJobDetailResponse(
        id=job.id,
        task_id=job.task_id,
        status=job.status,
        niche=job.niche,
        location=job.location,
        message=job.message,
        created_at=job.created_at.isoformat(),
        leads=[
            {
                "company_name": lead.company_name,
                "website": lead.website,
                "decision_maker_name": lead.decision_maker_name,
                "title": lead.title,
                "verified_email": lead.verified_email,
                "personal_phone": lead.personal_phone,
                "public_phone": lead.public_phone,
                "personal_phone_verified": bool(lead.personal_phone_verified),
                "public_phone_verified": bool(lead.public_phone_verified),
                "tech_stack": lead.tech_stack or [],
                "recent_news": lead.recent_news,
                "custom_icebreaker": lead.custom_icebreaker,
                "email_1_initial": lead.email_1_initial,
                "email_2_followup": lead.email_2_followup,
                "email_3_breakup": lead.email_3_breakup,
                "enrichment_source": lead.enrichment_source,
            }
            for lead in job.leads
        ],
    )


@app.post("/api/webhooks/configure", response_model=WebhookConfigureResponse)
async def configure_webhook(
    payload: WebhookConfigureRequest,
    _user: Annotated[User, Depends(get_current_user)],
) -> WebhookConfigureResponse:
    """Save the CRM webhook URL (authenticated)."""
    url = str(payload.webhook_url)
    try:
        set_webhook_url(url)
    except Exception as exc:
        logger.exception("Failed to save webhook URL")
        raise HTTPException(status_code=503, detail=f"Could not save webhook: {exc}") from exc

    logger.info("Webhook configured: %s", url)
    return WebhookConfigureResponse(webhook_url=url)


@app.get("/api/webhooks/configure", response_model=WebhookStatusResponse)
async def get_webhook_config(
    _user: Annotated[User, Depends(get_current_user)],
) -> WebhookStatusResponse:
    """Return the currently configured webhook URL."""
    url = get_webhook_url()
    return WebhookStatusResponse(webhook_url=url, configured=bool(url))


def _safe_meta(result: AsyncResult) -> dict[str, Any]:
    """Normalize Celery info/meta into a dict for progress fields."""
    info = result.info
    if isinstance(info, dict):
        return info
    return {}
