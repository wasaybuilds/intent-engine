"""Database persistence helpers for scrape jobs and leads."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.db import Lead, ScrapeJob, User


def create_scrape_job(
    db: Session,
    user: User,
    task_id: str,
    niche: str,
    location: str,
) -> ScrapeJob:
    """
    Persist a new scrape job in PENDING state.

    @param db - Database session
    @param user - Job owner
    @param task_id - Celery task id
    @param niche - Search niche
    @param location - Search location
    @returns Created ScrapeJob
    """
    job = ScrapeJob(
        task_id=task_id,
        user_id=user.id,
        status="PENDING",
        niche=niche,
        location=location,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_scrape_job_status(
    db: Session,
    task_id: str,
    status: str,
    message: str | None = None,
) -> ScrapeJob | None:
    """
    Update job status by Celery task id.

    @param db - Database session
    @param task_id - Celery task id
    @param status - New status string
    @param message - Optional completion/failure message
    @returns Updated job or None
    """
    job = db.query(ScrapeJob).filter(ScrapeJob.task_id == task_id).one_or_none()
    if not job:
        return None

    job.status = status
    if message is not None:
        job.message = message
    db.commit()
    db.refresh(job)
    return job


def save_leads_for_job(db: Session, task_id: str, leads: list[dict[str, Any]]) -> None:
    """
    Replace leads for a completed scrape job.

    @param db - Database session
    @param task_id - Celery task id
    @param leads - Final lead dicts from scraper pipeline
    """
    job = db.query(ScrapeJob).filter(ScrapeJob.task_id == task_id).one_or_none()
    if not job:
        return

    db.query(Lead).filter(Lead.scrape_job_id == job.id).delete()

    for row in leads:
        db.add(
            Lead(
                scrape_job_id=job.id,
                company_name=row.get("company_name", ""),
                website=row.get("website", ""),
                decision_maker_name=row.get("decision_maker_name", ""),
                title=row.get("title", ""),
                verified_email=row.get("verified_email", ""),
                tech_stack=row.get("tech_stack") or [],
                recent_news=row.get("recent_news"),
                custom_icebreaker=row.get("custom_icebreaker", ""),
                email_1_initial=row.get("email_1_initial", ""),
                email_2_followup=row.get("email_2_followup", ""),
                email_3_breakup=row.get("email_3_breakup", ""),
                enrichment_source=row.get("enrichment_source", "scrape"),
            )
        )

    db.commit()


def get_user_scrape_jobs(db: Session, user_id: int) -> list[ScrapeJob]:
    """
    List scrape jobs for a user, newest first.

    @param db - Database session
    @param user_id - Owner user id
    @returns Ordered scrape jobs
    """
    return (
        db.query(ScrapeJob)
        .options(selectinload(ScrapeJob.leads))
        .filter(ScrapeJob.user_id == user_id)
        .order_by(ScrapeJob.created_at.desc())
        .all()
    )


def get_scrape_job_for_user(db: Session, user_id: int, job_id: int) -> ScrapeJob | None:
    """
    Fetch a scrape job owned by the given user.

    @param db - Database session
    @param user_id - Owner user id
    @param job_id - Scrape job primary key
    @returns ScrapeJob with leads or None
    """
    return (
        db.query(ScrapeJob)
        .options(selectinload(ScrapeJob.leads))
        .filter(ScrapeJob.id == job_id, ScrapeJob.user_id == user_id)
        .one_or_none()
    )


def get_scrape_job_by_task_id(db: Session, user_id: int, task_id: str) -> ScrapeJob | None:
    """
    Fetch a scrape job by Celery task id for ownership checks.

    @param db - Database session
    @param user_id - Owner user id
    @param task_id - Celery task id
    @returns ScrapeJob or None
    """
    return (
        db.query(ScrapeJob)
        .filter(ScrapeJob.task_id == task_id, ScrapeJob.user_id == user_id)
        .one_or_none()
    )
