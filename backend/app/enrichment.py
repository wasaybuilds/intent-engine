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

DECISION_TITLE_PATTERN = re.compile(
    r"\b(ceo|chief executive|founder|co-founder|owner|president|managing director)\b",
    re.IGNORECASE,
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
    Query Hunter.io Domain Search for executive contacts.

    @param domain - Target company domain
    @returns Best matching FallbackContact
    """
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": settings.hunter_api_key,
        "limit": 20,
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params=params)
        # Hunter returns 400 for some domains / plan limits — treat as no contact
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

    ranked: list[tuple[int, FallbackContact]] = []

    for entry in emails:
        if not isinstance(entry, dict):
            continue

        first = str(entry.get("first_name", "")).strip()
        last = str(entry.get("last_name", "")).strip()
        position = str(entry.get("position", "")).strip()
        email = str(entry.get("value", "")).strip()

        name = f"{first} {last}".strip()
        if len(name.split()) < 2 or not position:
            continue
        if not DECISION_TITLE_PATTERN.search(position) and not TITLE_KEYWORDS.search(position):
            continue

        score = _title_priority(position)
        ranked.append(
            (
                score,
                FallbackContact(
                    decision_maker_name=name,
                    title=position,
                    verified_email=email,
                    source="hunter.io",
                ),
            )
        )

    if not ranked:
        return None

    ranked.sort(key=lambda row: row[0])
    return ranked[0][1]


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
        if len(name.split()) < 2 or not title:
            continue

        return FallbackContact(
            decision_maker_name=name,
            title=title,
            verified_email=email,
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
    if "owner" in lower:
        return 2
    if "president" in lower:
        return 3
    return 4
