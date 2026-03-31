"""Pydantic models for the lead scraper API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    """Request payload for initiating a lead scrape."""

    niche: str = Field(..., min_length=1, description="Target business niche")
    location: str = Field(..., min_length=1, description="Geographic location to search")


class LeadResult(BaseModel):
    """A single enriched lead with intent signals and personalization."""

    company_name: str
    website: str = ""
    decision_maker_name: str
    title: str
    verified_email: str
    tech_stack: list[str] = Field(default_factory=list)
    recent_news: Optional[str] = None
    custom_icebreaker: str = ""
    email_1_initial: str = ""
    email_2_followup: str = ""
    email_3_breakup: str = ""
    enrichment_source: str = "scrape"


class ScrapeResponse(BaseModel):
    """Final scrape payload embedded in a completed task result."""

    leads: list[LeadResult]
    total: int
    message: str = ""


class TaskSubmitResponse(BaseModel):
    """Immediate acknowledgment when a scrape job is enqueued."""

    task_id: str
    status: Literal["PENDING"] = "PENDING"


class TaskProgress(BaseModel):
    """Live progress metadata while a scrape job runs."""

    step: str = ""
    detail: str = ""
    percent: int = Field(default=0, ge=0, le=100)
    companies_found: int = 0
    companies_processed: int = 0


class TaskStatusResponse(BaseModel):
    """
    Pollable task status for the frontend.

    status values map to Celery states (PENDING, STARTED, PROGRESS, SUCCESS, FAILURE).
    """

    task_id: str
    status: str
    progress: Optional[TaskProgress] = None
    result: Optional[ScrapeResponse] = None
    error: Optional[str] = None


class WebhookConfigureRequest(BaseModel):
    """Payload to save a CRM / email sequencer webhook URL."""

    webhook_url: HttpUrl


class WebhookConfigureResponse(BaseModel):
    """Confirmation after webhook URL is saved."""

    webhook_url: str
    message: str = "Webhook URL configured successfully."


class WebhookStatusResponse(BaseModel):
    """Current webhook configuration (if any)."""

    webhook_url: Optional[str] = None
    configured: bool = False


class ScrapeJobSummary(BaseModel):
    """Summary row for a user's scrape history."""

    id: int
    task_id: str
    status: str
    niche: str
    location: str
    message: Optional[str] = None
    lead_count: int = 0
    created_at: str


class ScrapeHistoryResponse(BaseModel):
    """List of past scrape jobs for the authenticated user."""

    jobs: list[ScrapeJobSummary]
    total: int


class ScrapeJobDetailResponse(BaseModel):
    """Full scrape job with persisted leads."""

    id: int
    task_id: str
    status: str
    niche: str
    location: str
    message: Optional[str] = None
    created_at: str
    leads: list[LeadResult]
