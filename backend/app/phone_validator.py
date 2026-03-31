"""Phone normalization and dual-pass verification (Apollo-style confidence)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Loose capture of phone-like strings in HTML / Maps labels
PHONE_CANDIDATE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]*)?(?:\(?\d{2,4}\)?[\s\-.]*)?\d{3,4}[\s\-.]+\d{3,4}"
    r"|\+\d{10,15}"
    r"|(?:\(?\d{3}\)?[\s\-.]*)\d{3}[\s\-.]+\d{4}",
)

MOBILE_HINT_RE = re.compile(
    r"\b(mobile|cell|cellular|direct|personal|owner.?s?\s*phone|private|whatsapp)\b",
    re.IGNORECASE,
)

PUBLIC_HINT_RE = re.compile(
    r"\b(office|main|front.?desk|reception|company|business|toll.?free|fax|hq)\b",
    re.IGNORECASE,
)

# North American toll-free prefixes — never treat as personal/owner mobiles
TOLL_FREE_NANP = frozenset({"800", "888", "877", "866", "855", "844", "833", "822"})

# Source reliability used when choosing among multiple candidates
SOURCE_PRIORITY = {
    "apollo.io": 0,
    "hunter.io": 1,
    "google_maps": 2,
    "website_owner": 3,
    "public_web_owner": 4,
    "website": 5,
    "public_web": 6,
}


@dataclass
class VerifiedPhone:
    """A phone number that passed two structural validation passes."""

    number: str
    e164: str
    line_type: str  # "personal" | "public"
    verified: bool
    verification_passes: int
    source: str = ""
    number_kind: str = ""  # mobile | fixed_line | toll_free | unknown


def clean_phone_raw(raw: str) -> str:
    """
    Normalize a raw tel: / Maps phone string before verification.

    Strips tel: prefix, URI encoding, extensions, and pause characters.

    @param raw - Dirty phone string
    @returns Cleaned candidate
    """
    if not raw:
        return ""

    value = unquote(raw).strip()
    if value.lower().startswith("tel:"):
        value = value[4:]
    # Drop ;ext= / ,,,, extensions that break parsers
    value = re.split(r"[;]", value, maxsplit=1)[0]
    value = value.replace(" ", " ").strip()
    return value


def extract_phone_candidates(text: str) -> list[str]:
    """
    Pull raw phone-like strings from free text or HTML.

    @param text - Page text or attribute value
    @returns Deduped raw candidates
    """
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for match in PHONE_CANDIDATE_RE.finditer(text):
        raw = clean_phone_raw(match.group(0))
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 10 or digits in seen:
            continue
        seen.add(digits)
        found.append(raw)
    return found


def extract_tel_hrefs(html: str) -> list[str]:
    """
    Extract phone numbers from tel: links in HTML.

    @param html - Raw HTML
    @returns Raw phone strings from hrefs
    """
    if not html:
        return []

    phones: list[str] = []
    for match in re.finditer(r'href=["\']tel:([^"\']+)["\']', html, re.IGNORECASE):
        cleaned = clean_phone_raw(match.group(1))
        if cleaned:
            phones.append(cleaned)
    return phones


def extract_phones_near_name(text: str, person_name: str) -> list[str]:
    """
    Find phone numbers in a text window around a decision-maker's name.

    Professional scrapers use name proximity as a weak personal-phone signal.

    @param text - Page plain text
    @param person_name - Full name to search near
    @returns Candidate phone strings
    """
    if not text or not person_name or len(person_name.split()) < 2:
        return []

    # Prefer last-name match windows (more unique on about pages)
    tokens = [t for t in person_name.split() if len(t) > 1]
    needles = [person_name, tokens[-1]] if tokens else [person_name]
    found: list[str] = []
    seen: set[str] = set()

    lower = text.lower()
    for needle in needles:
        start = 0
        needle_l = needle.lower()
        while True:
            idx = lower.find(needle_l, start)
            if idx < 0:
                break
            window = text[max(0, idx - 120) : idx + len(needle) + 160]
            for candidate in extract_phone_candidates(window):
                digits = re.sub(r"\D", "", candidate)
                if digits not in seen:
                    seen.add(digits)
                    found.append(candidate)
            start = idx + len(needle)

    return found


def classify_phone_context(raw: str, surrounding_text: str = "") -> str:
    """
    Guess personal vs public from nearby wording + number type.

    @param raw - Phone string
    @param surrounding_text - Nearby label / paragraph
    @returns "personal" or "public"
    """
    blob = f"{raw} {surrounding_text}"
    if MOBILE_HINT_RE.search(blob):
        return "personal"
    if PUBLIC_HINT_RE.search(blob):
        return "public"

    # A carrier type alone does not prove ownership. In North America,
    # libphonenumber commonly reports FIXED_LINE_OR_MOBILE for both business
    # and cell lines, so only explicit nearby labels can make a phone personal.
    kind = detect_number_kind(raw)
    if kind in {"fixed_line", "toll_free"}:
        return "public"
    return "public"


def detect_number_kind(raw: str, default_region: str = "US") -> str:
    """
    Classify a number as mobile / fixed_line / toll_free / unknown.

    @param raw - Phone string
    @param default_region - Default ISO region
    @returns Kind label
    """
    cleaned = clean_phone_raw(raw)
    digits = re.sub(r"\D", "", cleaned)

    # Fast NANP toll-free check
    if len(digits) == 11 and digits.startswith("1") and digits[1:4] in TOLL_FREE_NANP:
        return "toll_free"
    if len(digits) == 10 and digits[:3] in TOLL_FREE_NANP:
        return "toll_free"

    try:
        import phonenumbers
        from phonenumbers import NumberParseException, PhoneNumberType, number_type
    except ImportError:
        return "unknown"

    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except NumberParseException:
        return "unknown"

    ntype = number_type(parsed)
    if ntype in {
        PhoneNumberType.MOBILE,
        PhoneNumberType.FIXED_LINE_OR_MOBILE,
        PhoneNumberType.PERSONAL_NUMBER,
    }:
        return "mobile"
    if ntype == PhoneNumberType.TOLL_FREE:
        return "toll_free"
    if ntype in {PhoneNumberType.FIXED_LINE, PhoneNumberType.UAN, PhoneNumberType.VOIP}:
        return "fixed_line"
    return "unknown"


def verify_phone_twice(
    raw: str,
    *,
    line_type: str = "public",
    source: str = "",
    default_region: str = "US",
) -> Optional[VerifiedPhone]:
    """
    Validate a phone number in two structural passes.

    Pass 1 — structural parse + validity (phonenumbers).
    Pass 2 — re-parse E.164, possibility check, line-type sanity, optional Numverify.

    Only numbers that clear both passes are returned as verified.

    @param raw - Raw phone string
    @param line_type - personal | public
    @param source - Where the number was found
    @param default_region - ISO region for national numbers
    @returns VerifiedPhone or None
    """
    cleaned = clean_phone_raw(raw)
    if not cleaned:
        return None

    # ------------------------------------------------------------------
    # PASS 1: parse + is_valid_number
    # ------------------------------------------------------------------
    pass1 = _pass1_structural(cleaned, default_region)
    if not pass1:
        logger.debug("Phone pass-1 failed for %r", raw)
        return None

    e164, national_fmt = pass1
    kind = detect_number_kind(e164, default_region)

    # Personal/owner numbers must not be toll-free business lines
    if line_type == "personal" and kind == "toll_free":
        logger.debug("Rejecting toll-free as personal: %s", e164)
        return None

    # ------------------------------------------------------------------
    # PASS 2: re-parse E.164 + possibility + optional carrier API
    # ------------------------------------------------------------------
    pass2_ok = _pass2_confirm(e164, default_region, expected_line_type=line_type, kind=kind)
    if not pass2_ok:
        logger.debug("Phone pass-2 failed for %r (%s)", raw, e164)
        return None

    return VerifiedPhone(
        number=national_fmt,
        e164=e164,
        line_type=line_type if line_type in {"personal", "public"} else "public",
        verified=True,
        verification_passes=2,
        source=source,
        number_kind=kind,
    )


def _pass1_structural(raw: str, default_region: str) -> Optional[tuple[str, str]]:
    """
    First verification pass using the phonenumbers library.

    @returns (e164, national_format) or None
    """
    try:
        import phonenumbers
        from phonenumbers import NumberParseException, PhoneNumberFormat
    except ImportError:
        return _pass1_fallback_regex(raw)

    try:
        parsed = phonenumbers.parse(raw, default_region)
    except NumberParseException:
        cleaned = re.sub(r"[^\d+]", "", raw)
        if not cleaned:
            return None
        try:
            parsed = phonenumbers.parse(cleaned, default_region)
        except NumberParseException:
            return None

    if not phonenumbers.is_valid_number(parsed):
        return None

    e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    national = phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
    return e164, national


def _pass1_fallback_regex(raw: str) -> Optional[tuple[str, str]]:
    """Minimal digit-length check when phonenumbers is not installed."""
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        if len(digits) < 10 or len(digits) > 15:
            return None
        e164 = f"+{digits}"
    else:
        if len(digits) == 10:
            e164 = f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            e164 = f"+{digits}"
        else:
            return None
    return e164, e164


def _pass2_confirm(
    e164: str,
    default_region: str,
    *,
    expected_line_type: str,
    kind: str,
) -> bool:
    """
    Second structural validation pass.

    Re-parses the E.164 string, requires is_possible_number, enforces
    personal≠toll_free, and when NUMVERIFY_API_KEY is set confirms via API.
    """
    try:
        import phonenumbers
        from phonenumbers import NumberParseException, PhoneNumberFormat
    except ImportError:
        digits = re.sub(r"\D", "", e164)
        return 10 <= len(digits) <= 15

    try:
        again = phonenumbers.parse(e164, None)
    except NumberParseException:
        return False

    if not phonenumbers.is_possible_number(again):
        return False
    if not phonenumbers.is_valid_number(again):
        return False

    again_e164 = phonenumbers.format_number(again, PhoneNumberFormat.E164)
    if again_e164 != e164:
        return False

    # Independent kind re-check on the re-parsed number
    kind_again = detect_number_kind(again_e164, default_region)
    if expected_line_type == "personal" and kind_again == "toll_free":
        return False
    if kind == "toll_free" and kind_again != "toll_free" and expected_line_type == "personal":
        return False

    if settings.numverify_api_key:
        return _numverify_lookup(e164)

    return True


def _numverify_lookup(e164: str) -> bool:
    """
    Optional carrier-level confirmation via Numverify (Apilayer).

    @param e164 - E.164 number
    @returns True when API marks the number valid
    """
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.get(
                "https://apilayer.net/api/validate",
                params={
                    "access_key": settings.numverify_api_key,
                    "number": e164,
                    "format": 1,
                },
            )
            if response.status_code >= 400:
                logger.warning("Numverify HTTP %s — skipping API confirm", response.status_code)
                return True

            data = response.json()
            if data.get("valid") is True:
                return True
            logger.info("Numverify rejected %s: %s", e164, data.get("error") or data)
            return False
    except Exception as exc:
        logger.warning("Numverify lookup failed for %s: %s", e164, exc)
        return True


def _source_rank(source: str) -> int:
    """Lower = more trusted enrichment source."""
    return SOURCE_PRIORITY.get(source, 50)


def pick_best_phones(
    personal_candidates: list[tuple[str, str]],
    public_candidates: list[tuple[str, str]],
) -> tuple[Optional[VerifiedPhone], Optional[VerifiedPhone]]:
    """
    Dual-verify candidate lists and return at most one personal + one public.

    Candidates are tried in source-priority order (Apollo → Hunter → Maps → site).
    Mobile-typed numbers are preferred for personal; non-toll-free for public.

    @param personal_candidates - list of (raw, source)
    @param public_candidates - list of (raw, source)
    @returns (personal, public) VerifiedPhone pair
    """
    personal: Optional[VerifiedPhone] = None
    public: Optional[VerifiedPhone] = None
    used_e164: set[str] = set()

    personal_sorted = sorted(
        personal_candidates,
        key=lambda row: (
            _source_rank(row[1]),
            0 if detect_number_kind(row[0]) == "mobile" else 1,
        ),
    )
    public_sorted = sorted(
        public_candidates,
        key=lambda row: (
            _source_rank(row[1]),
            0 if detect_number_kind(row[0]) != "toll_free" else 1,
        ),
    )

    for raw, source in personal_sorted:
        verified = verify_phone_twice(raw, line_type="personal", source=source)
        if verified and verified.e164 not in used_e164:
            personal = verified
            used_e164.add(verified.e164)
            break

    for raw, source in public_sorted:
        verified = verify_phone_twice(raw, line_type="public", source=source)
        if verified and verified.e164 not in used_e164:
            public = verified
            used_e164.add(verified.e164)
            break

    return personal, public
