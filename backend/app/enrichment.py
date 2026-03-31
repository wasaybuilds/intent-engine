"""Third-party API fallback when website scraping fails to find decision makers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
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
    # Raw personal / direct-dial candidates from the enrichment provider
    personal_phones: list[str] = field(default_factory=list)
    # Raw company / HQ phones when the provider returns them
    public_phones: list[str] = field(default_factory=list)


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


def enrich_phones_for_person(
    domain: str,
    decision_maker_name: str,
) -> tuple[list[str], list[str]]:
    """
    Look up personal + public phones for a known person via Apollo/Hunter.

    Tries Apollo people/match (phone reveal) first — search alone often returns
    empty phone_numbers on lower tiers. Falls back to domain search.

    @param domain - Company domain
    @param decision_maker_name - Full name
    @returns (personal_phones, public_phones) raw lists
    """
    personal: list[str] = []
    public: list[str] = []

    if settings.apollo_api_key and decision_maker_name and domain:
        try:
            contact = _apollo_people_match(domain, decision_maker_name)
            if contact:
                personal.extend(contact.personal_phones)
                public.extend(contact.public_phones)
        except Exception as exc:
            logger.warning("Apollo people/match failed for %s: %s", decision_maker_name, exc)

        if not personal:
            try:
                contact = _apollo_person_search(domain, decision_maker_name)
                if contact:
                    personal.extend(contact.personal_phones)
                    public.extend(contact.public_phones)
            except Exception as exc:
                logger.warning("Apollo phone search failed for %s: %s", decision_maker_name, exc)

    if settings.hunter_api_key and domain and not personal:
        try:
            contact = _hunter_domain_search(domain)
            if contact and _names_match(contact.decision_maker_name, decision_maker_name):
                personal.extend(contact.personal_phones)
                public.extend(contact.public_phones)
        except Exception as exc:
            logger.warning("Hunter phone lookup failed for %s: %s", domain, exc)

    return personal, public


def _apollo_people_match(domain: str, full_name: str) -> Optional[FallbackContact]:
    """
    Apollo People Match with phone reveal — the professional phone lookup path.

    Search endpoints frequently omit phones; match + reveal_phone_number is how
    Apollo clients obtain mobiles (consumes phone credits when available).

    @param domain - Company domain
    @param full_name - Decision maker full name
    @returns FallbackContact with phones when Apollo returns them
    """
    parts = [p for p in full_name.strip().split() if p]
    if len(parts) < 2:
        return None

    url = "https://api.apollo.io/api/v1/people/match"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.apollo_api_key,
    }
    payload = {
        "first_name": parts[0],
        "last_name": parts[-1],
        "organization_name": "",
        "domain": domain,
        "reveal_phone_number": True,
        "reveal_personal_emails": False,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            logger.info(
                "Apollo people/match %s for %s@%s: %s",
                response.status_code,
                full_name,
                domain,
                response.text[:240],
            )
            return None
        data = response.json()

    person = data.get("person")
    if not isinstance(person, dict):
        return None

    first = str(person.get("first_name", "")).strip() or parts[0]
    last = str(person.get("last_name", "")).strip() or parts[-1]
    title = str(person.get("title", "")).strip()
    email = str(person.get("email", "")).strip()
    personal_phones, public_phones = _apollo_extract_phones(person)

    if not personal_phones and not public_phones and not email:
        return None

    return FallbackContact(
        decision_maker_name=f"{first} {last}".strip(),
        title=title or "Decision Maker",
        verified_email=email if email and email != "unavailable" else "",
        source="apollo.io",
        personal_phones=personal_phones,
        public_phones=public_phones,
    )


def _names_match(a: str, b: str) -> bool:
    """Loose first+last token overlap check."""
    ta = {t.lower() for t in a.split() if len(t) > 1}
    tb = {t.lower() for t in b.split() if len(t) > 1}
    return len(ta & tb) >= 2


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

    # Organization-level phone from Hunter organization block
    org_phone = ""
    org = data.get("data", {}).get("organization") or data.get("data", {})
    if isinstance(org, dict):
        org_phone = str(org.get("phone") or org.get("phone_number") or "").strip()

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
        person_phone = str(
            entry.get("phone_number")
            or entry.get("phone")
            or ""
        ).strip()

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
            personal_phones=[person_phone] if person_phone else [],
            public_phones=[org_phone] if org_phone else [],
        )

        if position and (
            DECISION_TITLE_PATTERN.search(position) or TITLE_KEYWORDS.search(position)
        ):
            executives.append((_title_priority(position), contact))
        elif email_type == "personal" or (first and last):
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
    return _apollo_people_query(
        {
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
    )


def _apollo_person_search(domain: str, full_name: str) -> Optional[FallbackContact]:
    """
    Query Apollo for a specific person at a domain to obtain phone numbers.

    @param domain - Company domain
    @param full_name - Decision maker name
    @returns FallbackContact with phones when found
    """
    parts = full_name.strip().split()
    payload: dict = {
        "q_organization_domains": domain,
        "page": 1,
        "per_page": 5,
    }
    if len(parts) >= 2:
        payload["q_person_name"] = full_name
    return _apollo_people_query(payload)


def _apollo_people_query(payload: dict) -> Optional[FallbackContact]:
    """
    Shared Apollo mixed_people/search caller.

    @param payload - Apollo search body
    @returns First usable FallbackContact
    """
    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": settings.apollo_api_key,
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

        personal_phones, public_phones = _apollo_extract_phones(person)

        return FallbackContact(
            decision_maker_name=name,
            title=title or "Decision Maker",
            verified_email=email if email and email != "unavailable" else "",
            source="apollo.io",
            personal_phones=personal_phones,
            public_phones=public_phones,
        )

    return None


def _apollo_extract_phones(person: dict) -> tuple[list[str], list[str]]:
    """
    Split Apollo phone_numbers into personal (mobile/direct) vs public (work/hq).

    @param person - Apollo person object
    @returns (personal, public) raw number lists
    """
    personal: list[str] = []
    public: list[str] = []

    numbers = person.get("phone_numbers") or []
    if isinstance(numbers, list):
        for entry in numbers:
            if not isinstance(entry, dict):
                continue
            raw = str(
                entry.get("sanitized_number")
                or entry.get("raw_number")
                or entry.get("number")
                or ""
            ).strip()
            if not raw:
                continue
            ptype = str(entry.get("type") or entry.get("position_type") or "").lower()
            if ptype in {"mobile", "cell", "cellular", "direct_dial", "direct", "personal"}:
                personal.append(raw)
            else:
                # work / hq / other — treat as public unless clearly mobile
                public.append(raw)

    # Legacy single-field phones
    for key in ("mobile_phone", "personal_phone", "direct_phone"):
        value = str(person.get(key) or "").strip()
        if value:
            personal.append(value)

    org = person.get("organization")
    if isinstance(org, dict):
        org_phone = str(org.get("phone") or org.get("primary_phone") or "").strip()
        if org_phone:
            public.append(org_phone)

    return personal, public


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
