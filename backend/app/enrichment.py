"""Third-party API fallback when website scraping fails to find decision makers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings
from app.email_validator import TITLE_KEYWORDS

logger = logging.getLogger(__name__)

# Free Hunter plans reject limit > 10 — keep within that ceiling
HUNTER_RESULT_LIMIT = 10

DECISION_TITLE_PATTERN = re.compile(
    r"\b("
    r"ceo|chief executive|founder|co-?founder|owner|president|"
    r"managing director|general manager|operations manager|manager|"
    r"director|principal|partner|proprietor"
    r")\b",
    re.IGNORECASE,
)

GENERIC_LOCAL_PARTS = frozenset(
    {
        "info",
        "contact",
        "hello",
        "support",
        "sales",
        "admin",
        "office",
        "team",
        "help",
        "enquiries",
        "inquiries",
        "mail",
        "general",
        "noreply",
        "no-reply",
    }
)


@dataclass
class FallbackContact:
    """Decision maker returned by a third-party enrichment API."""

    decision_maker_name: str
    title: str
    verified_email: str = ""
    source: str = ""


def fallback_enrich_decision_maker(domain: str, company_name: str = "") -> Optional[FallbackContact]:
    """
    Attempt Hunter.io then Apollo when scrape + LLM find no decision maker.

    @param domain - Company email domain
    @param company_name - Company name for logging
    @returns FallbackContact or None
    """
    if not domain:
        return None

    if settings.hunter_api_key:
        try:
            contact = _hunter_domain_search(domain)
            if contact:
                logger.info(
                    "Hunter.io fallback found %s for %s",
                    contact.decision_maker_name,
                    company_name or domain,
                )
                return contact
        except Exception as exc:
            logger.warning("Hunter.io fallback failed for %s: %s", domain, exc)

    if settings.apollo_api_key:
        try:
            contact = _apollo_domain_search(domain)
            if contact:
                logger.info(
                    "Apollo fallback found %s for %s",
                    contact.decision_maker_name,
                    company_name or domain,
                )
                return contact
        except Exception as exc:
            logger.warning("Apollo fallback failed for %s: %s", domain, exc)

    return None


def _hunter_domain_search(domain: str) -> Optional[FallbackContact]:
    """
    Query Hunter.io Domain Search for executive (or best available) contacts.

    Free plans only allow up to 10 results — requesting more returns HTTP 400.

    @param domain - Target company domain
    @returns Best matching FallbackContact
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": settings.hunter_api_key,
        "limit": HUNTER_RESULT_LIMIT,
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params=params)
        if response.status_code >= 400:
            logger.warning(
                "Hunter.io domain-search %s for %s: %s",
                response.status_code,
                domain,
                response.text[:300],
            )
            return None
        data = response.json()

    emails = data.get("data", {}).get("emails", [])
    if not isinstance(emails, list):
        return None

    executives: list[tuple[int, FallbackContact]] = []
    personal_fallback: list[FallbackContact] = []

    for entry in emails:
        if not isinstance(entry, dict):
            continue

        first = str(entry.get("first_name", "") or "").strip()
        last = str(entry.get("last_name", "") or "").strip()
        position = str(entry.get("position", "") or "").strip()
        email = str(entry.get("value", "") or "").strip()
        email_type = str(entry.get("type", "") or "").strip().lower()

        name = f"{first} {last}".strip()
        if len(name.split()) < 2 or not email:
            continue

        local_part = email.split("@", 1)[0].lower()
        if local_part in GENERIC_LOCAL_PARTS:
            continue

        contact = FallbackContact(
            decision_maker_name=name,
            title=position or "Team Member",
            verified_email=email,
            source="hunter.io",
        )

        if position and (
            DECISION_TITLE_PATTERN.search(position) or TITLE_KEYWORDS.search(position)
        ):
            executives.append((_title_priority(position), contact))
        elif email_type == "personal" or (first and last):
            # Keep named personal emails even without a C-suite title
            personal_fallback.append(contact)

    if executives:
        executives.sort(key=lambda row: row[0])
        return executives[0][1]

    if personal_fallback:
        logger.info(
            "Hunter.io: no executive title match for %s — using best named contact",
            domain,
        )
        return personal_fallback[0]

    return None


def _apollo_domain_search(domain: str) -> Optional[FallbackContact]:
    """
    Query Apollo mixed people search for CEO/Founder at a domain.

    @param domain - Target company domain
    @returns Best matching FallbackContact
    """
    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.apollo_api_key,
    }
    payload = {
        "q_organization_domains": domain,
        "person_titles": [
            "CEO",
            "Chief Executive Officer",
            "Founder",
            "Co-Founder",
            "Owner",
            "President",
            "Managing Director",
            "General Manager",
        ],
        "page": 1,
        "per_page": 5,
    }

    with httpx.Client(timeout=25.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    people = data.get("people", [])
    if not isinstance(people, list):
        return None

    for person in people:
        if not isinstance(person, dict):
            continue

        first = str(person.get("first_name", "")).strip()
        last = str(person.get("last_name", "")).strip()
        title = str(person.get("title", "")).strip()
        email = str(person.get("email", "")).strip()

        name = f"{first} {last}".strip()
        if len(name.split()) < 2:
            continue

        return FallbackContact(
            decision_maker_name=name,
            title=title or "Decision Maker",
            verified_email=email if email and email != "unavailable" else "",
            source="apollo.io",
        )

    return None


def _title_priority(title: str) -> int:
    """Lower score = higher priority decision-maker title."""
    lower = title.lower()
    if "ceo" in lower or "chief executive" in lower:
        return 0
    if "founder" in lower:
        return 1
    if "owner" in lower or "proprietor" in lower:
        return 2
    if "president" in lower:
        return 3
    if "general manager" in lower or "managing director" in lower:
        return 4
    if "manager" in lower:
        return 5
    return 6
