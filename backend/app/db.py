"""PostgreSQL connection, session factory, and SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Generator

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class User(Base):
    """Authenticated user synced from Clerk."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    scrape_jobs: Mapped[list["ScrapeJob"]] = relationship(
        "ScrapeJob", back_populates="user", cascade="all, delete-orphan"
    )


class ScrapeJob(Base):
    """A single scrape run initiated by a user."""

    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)
    niche: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="scrape_jobs")
    leads: Mapped[list["Lead"]] = relationship(
        "Lead", back_populates="scrape_job", cascade="all, delete-orphan"
    )


class Lead(Base):
    """An enriched lead record tied to a scrape job."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scrape_job_id: Mapped[int] = mapped_column(ForeignKey("scrape_jobs.id"), index=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    decision_maker_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    verified_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    tech_stack: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recent_news: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_icebreaker: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_1_initial: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_2_followup: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_3_breakup: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enrichment_source: Mapped[str] = mapped_column(String(64), nullable=False, default="scrape")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    scrape_job: Mapped["ScrapeJob"] = relationship("ScrapeJob", back_populates="leads")


def init_db() -> None:
    """Create all tables and apply lightweight column migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate_lead_columns()


def _migrate_lead_columns() -> None:
    """Add Phase 5 columns to existing leads tables without Alembic."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "leads" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("leads")}
    additions = {
        "email_1_initial": "TEXT DEFAULT ''",
        "email_2_followup": "TEXT DEFAULT ''",
        "email_3_breakup": "TEXT DEFAULT ''",
        "enrichment_source": "VARCHAR(64) DEFAULT 'scrape'",
    }

    with engine.begin() as conn:
        for column, ddl in additions.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {column} {ddl}"))


def get_db() -> Generator:
    """
    Yield a database session for FastAPI dependency injection.

    @yields SQLAlchemy session closed after request
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
