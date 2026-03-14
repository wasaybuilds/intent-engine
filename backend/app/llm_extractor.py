"""LLM-powered decision-maker extraction and cold email sequence generation."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings
from app.email_validator import TITLE_KEYWORDS

logger = logging.getLogger(__name__)

# Kept as a safety net when LLM is unavailable or returns empty
_NAME_TITLE_PATTERNS = [
    re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*[,–\-|]\s*"
        r"(CEO|Chief Executive Officer|Founder|Co-Founder|Owner|President|"
        r"Managing Director|Director)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(CEO|Chief Executive Officer|Founder|Co-Founder|Owner|President|"
        r"Managing Director|Director)\s*[,–\-|:]\s*"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        re.IGNORECASE,
    ),
    re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\n\s*"
        r"(CEO|Chief Executive Officer|Founder|Co-Founder|Owner|President|"
        r"Managing Director|Director)",
        re.IGNORECASE,
    ),
]

EXTRACTION_SYSTEM_PROMPT = """You extract B2B decision makers from company website text.
Return ONLY valid JSON matching this schema exactly:
{
  "decision_makers": [
    { "name": "string", "title": "string", "relevance_score": 1-10 }
  ]
}

Rules:
- Only include real people with titles such as CEO, Founder, Co-Founder, Owner,
  President, Managing Director, Director, or equivalent decision-maker roles.
- Ignore generic contacts (info@, support, sales teams without named people).
- relevance_score: 10 = CEO/Founder, 7-9 = Owner/President, 4-6 = Director, 1-3 = weak match.
- If none found, return {"decision_makers": []}.
- Do not invent names. Only extract what is clearly present in the text."""

ICEBREAKER_SYSTEM_PROMPT = """You write hyper-personalized B2B cold email campaigns.
Return ONLY valid JSON matching this schema exactly:
{
  "email_1_initial": "Subject: ...\\n\\nBody: ...",
  "email_2_followup": "Body: ...",
  "email_3_breakup": "Body: ..."
}

Rules for email_1_initial:
- Include a compelling Subject line prefixed with "Subject: "
- Then a blank line, then "Body: " followed by the email body
- Reference tech stack, recent news, or the decision maker's role when available
- Conversational, specific, non-salesy, under 120 words

Rules for email_2_followup:
- Prefix with "Body: "
- Short follow-up (2-4 sentences) referencing email 1 without being pushy
- Add one new value point or insight

Rules for email_3_breakup:
- Prefix with "Body: "
- Polite breakup email (2-3 sentences), leave door open
- No guilt trips

General:
- Do NOT use placeholders like [Name] or {{company}} — use real names provided
- Do NOT start with "I hope this email finds you well."
- Write as if sending to the decision maker directly"""


@dataclass
class EmailSequence:
    """Three-step cold email campaign for a single lead."""

    email_1_initial: str = ""
    email_2_followup: str = ""
    email_3_breakup: str = ""
    custom_icebreaker: str = ""


def extract_decision_makers(
    page_text: str,
    company_name: str = "",
) -> list[tuple[str, str, int]]:
    """
    Extract decision makers from cleaned page text.

    Prefers an OpenAI-compatible LLM when configured; falls back to regex.

    @param page_text - Plain text from About/Team/Contact pages
    @param company_name - Company context for the prompt
    @returns List of (name, title, relevance_score) tuples
    """
    cleaned = _truncate_text(page_text)
    if not cleaned.strip():
        return []

    if settings.llm_enabled:
        try:
            results = _extract_via_llm(cleaned, company_name)
            if results:
                return results
            logger.info("LLM returned no decision makers; trying regex fallback")
        except Exception as exc:
            logger.warning("LLM extraction failed (%s); using regex fallback", exc)

    return _extract_via_regex(cleaned)


def generate_email_sequence(
    company_name: str,
    decision_maker_name: str,
    title: str,
    tech_stack: list[str],
    recent_news: Optional[str] = None,
    niche: str = "",
) -> EmailSequence:
    """
    Generate a full 3-step cold email campaign for a decision maker.

    @param company_name - Target company
    @param decision_maker_name - Person's full name
    @param title - Job title
    @param tech_stack - Detected SaaS footprints
    @param recent_news - Most recent blog/news headline
    @param niche - Search niche for extra context
    @returns EmailSequence with all three emails plus icebreaker snippet
    """
    if not decision_maker_name or not title:
        return EmailSequence()

    if settings.llm_enabled:
        try:
            return _generate_sequence_via_llm(
                company_name=company_name,
                decision_maker_name=decision_maker_name,
                title=title,
                tech_stack=tech_stack,
                recent_news=recent_news,
                niche=niche,
            )
        except Exception as exc:
            logger.warning("Email sequence generation failed (%s); using template fallback", exc)

    return _fallback_email_sequence(company_name, decision_maker_name, title, tech_stack, recent_news)


def generate_icebreaker(
    company_name: str,
    decision_maker_name: str,
    title: str,
    tech_stack: list[str],
    recent_news: Optional[str] = None,
    niche: str = "",
) -> str:
    """
    Backward-compatible wrapper returning the opening line from the email sequence.

    @returns First-sentence icebreaker derived from email_1
    """
    sequence = generate_email_sequence(
        company_name, decision_maker_name, title, tech_stack, recent_news, niche
    )
    return sequence.custom_icebreaker


def _generate_sequence_via_llm(
    company_name: str,
    decision_maker_name: str,
    title: str,
    tech_stack: list[str],
    recent_news: Optional[str],
    niche: str,
) -> EmailSequence:
    """Call LLM to produce a 3-step email campaign."""
    context_lines = [
        f"Company: {company_name}",
        f"Decision maker: {decision_maker_name}",
        f"Title: {title}",
        f"Tech stack: {', '.join(tech_stack) if tech_stack else 'Unknown'}",
        f"Recent news/blog: {recent_news or 'None found'}",
    ]
    if niche:
        context_lines.append(f"Search niche: {niche}")

    user_prompt = "\n".join(context_lines) + "\n\nWrite the 3-step email sequence JSON."

    payload = {
        "model": settings.llm_model,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": ICEBREAKER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    content = _call_llm(payload)
    parsed = _parse_json_content(content)

    email_1 = str(parsed.get("email_1_initial", "")).strip()
    email_2 = str(parsed.get("email_2_followup", "")).strip()
    email_3 = str(parsed.get("email_3_breakup", "")).strip()

    return EmailSequence(
        email_1_initial=email_1,
        email_2_followup=email_2,
        email_3_breakup=email_3,
        custom_icebreaker=_extract_icebreaker_from_email(email_1),
    )


def _extract_icebreaker_from_email(email_1: str) -> str:
    """Pull the first sentence from email_1 body as a short icebreaker snippet."""
    body = email_1
    if "Body:" in email_1:
        body = email_1.split("Body:", 1)[1].strip()

    if not body:
        return ""

    first_sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0].strip()
    return first_sentence[:280]


def _fallback_email_sequence(
    company_name: str,
    decision_maker_name: str,
    title: str,
    tech_stack: list[str],
    recent_news: Optional[str],
) -> EmailSequence:
    """Template-based 3-step sequence when LLM is unavailable."""
    opener = _fallback_icebreaker(company_name, title, tech_stack, recent_news)

    email_1 = (
        f"Subject: Quick question for {company_name}\n\n"
        f"Body: Hi {decision_maker_name.split()[0]},\n\n"
        f"{opener}\n\n"
        f"Would you be open to a brief conversation this week?"
    )
    email_2 = (
        f"Body: Hi {decision_maker_name.split()[0]},\n\n"
        f"Just bumping my note from earlier — happy to share how similar "
        f"{title}s in your space are tackling this. Worth a 10-minute chat?"
    )
    email_3 = (
        f"Body: Hi {decision_maker_name.split()[0]},\n\n"
        f"I'll assume timing isn't right at {company_name}. Feel free to reach "
        f"out if priorities shift — always happy to help."
    )

    return EmailSequence(
        email_1_initial=email_1,
        email_2_followup=email_2,
        email_3_breakup=email_3,
        custom_icebreaker=opener,
    )


def _generate_icebreaker_via_llm(
    company_name: str,
    decision_maker_name: str,
    title: str,
    tech_stack: list[str],
    recent_news: Optional[str],
    niche: str,
) -> str:
    """Legacy LLM icebreaker path — delegates to sequence generator."""
    return generate_email_sequence(
        company_name, decision_maker_name, title, tech_stack, recent_news, niche
    ).custom_icebreaker


def _fallback_icebreaker(
    company_name: str,
    title: str,
    tech_stack: list[str],
    recent_news: Optional[str],
) -> str:
    """Template-based icebreaker when LLM is unavailable."""
    if recent_news:
        return (
            f"Saw that {company_name} recently published \"{recent_news}\" — "
            f"would love to hear how that's shaping your priorities as {title}."
        )
    if tech_stack:
        stack = tech_stack[0]
        return (
            f"Noticed {company_name} is running on {stack} — curious if you're "
            f"exploring ways to get more out of your stack this quarter."
        )
    return (
        f"I've been following {company_name} and wanted to reach out given your "
        f"role as {title}."
    )


def _truncate_text(text: str, max_chars: int = 12_000) -> str:
    """Cap token cost while keeping the start of the page (usually leadership)."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n…[truncated]"


def _call_llm(payload: dict) -> str:
    """Execute an OpenAI-compatible chat completions request."""
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]


def _parse_json_content(content: str) -> dict:
    """Strip markdown fences and parse JSON object."""
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    parsed = json.loads(stripped)
    return parsed if isinstance(parsed, dict) else {}


def _extract_via_llm(page_text: str, company_name: str) -> list[tuple[str, str, int]]:
    """Call LLM for decision-maker extraction."""
    user_prompt = (
        f"Company: {company_name or 'Unknown'}\n\n"
        f"Website text:\n{page_text}\n\n"
        "Extract decision makers as JSON."
    )

    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    content = _call_llm(payload)
    return _parse_decision_makers_json(content)


def _parse_decision_makers_json(content: str) -> list[tuple[str, str, int]]:
    """Parse decision_makers array from LLM JSON."""
    parsed = _parse_json_content(content)
    makers = parsed.get("decision_makers", [])
    if not isinstance(makers, list):
        return []

    results: list[tuple[str, str, int]] = []
    seen: set[str] = set()

    for item in makers:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        title = str(item.get("title", "")).strip()
        try:
            score = int(item.get("relevance_score", 5))
        except (TypeError, ValueError):
            score = 5

        score = max(1, min(10, score))

        if len(name.split()) < 2 or not title:
            continue
        if name.lower() in seen:
            continue

        seen.add(name.lower())
        results.append((name, title, score))

    results.sort(key=lambda row: row[2], reverse=True)
    return results


def _extract_via_regex(text: str) -> list[tuple[str, str, int]]:
    """Regex heuristic fallback used when LLM is off or empty."""
    matches: list[tuple[str, str, int]] = []
    seen: set[str] = set()

    for pattern in _NAME_TITLE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) != 2:
                continue

            if TITLE_KEYWORDS.search(groups[0]):
                title, name = groups[0], groups[1]
            else:
                name, title = groups[0], groups[1]

            name = name.strip()
            title = title.strip()
            if len(name.split()) < 2 or name.lower() in seen:
                continue

            seen.add(name.lower())
            matches.append((name, title, _score_title(title)))

    matches.sort(key=lambda row: row[2], reverse=True)
    return matches


def _score_title(title: str) -> int:
    """Map title keywords to a 1–10 relevance score for ranking."""
    lower = title.lower()
    if "ceo" in lower or "chief executive" in lower:
        return 10
    if "founder" in lower:
        return 9
    if "owner" in lower:
        return 8
    if "president" in lower:
        return 7
    if "managing director" in lower:
        return 6
    if "director" in lower:
        return 5
    return 3


def pick_best_decision_maker(
    candidates: list[tuple[str, str, int]],
) -> Optional[tuple[str, str]]:
    """
    Select the highest-scoring decision maker.

    @param candidates - (name, title, score) list
    @returns (name, title) or None
    """
    if not candidates:
        return None
    name, title, _ = candidates[0]
    return name, title
