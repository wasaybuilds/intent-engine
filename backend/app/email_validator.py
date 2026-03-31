"""Email permutation generation and SMTP/MX validation utilities."""

from __future__ import annotations

import logging
import re
import smtplib
import socket
from typing import Optional

import dns.resolver

logger = logging.getLogger(__name__)

# Generic inboxes we deliberately skip
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
    }
)

TITLE_KEYWORDS = re.compile(
    r"\b("
    r"CEO|Chief Executive Officer|Founder|Co-Founder|Owner|President|"
    r"Managing Director|General Manager|Operations Manager|Manager|"
    r"Director|Managing Partner|Principal|Partner|Proprietor"
    r")\b",
    re.IGNORECASE,
)


def extract_domain(url: str) -> Optional[str]:
    """
    Extract a bare domain from a URL string.

    @param url - Full or partial website URL
    @returns Domain without scheme or www prefix, or None if invalid
    """
    if not url:
        return None

    cleaned = url.strip().lower()
    cleaned = re.sub(r"^https?://", "", cleaned)
    cleaned = re.sub(r"^www\.", "", cleaned)
    cleaned = cleaned.split("/")[0].split("?")[0]

    if "." not in cleaned:
        return None

    return cleaned


def generate_email_permutations(full_name: str, domain: str) -> list[str]:
    """
    Build common B2B email format permutations for a person's name.

    @param full_name - Decision maker's full name
    @param domain - Company email domain
    @returns Ordered list of candidate email addresses
    """
    parts = re.sub(r"[^a-zA-Z\s\-']", "", full_name).strip().split()
    if len(parts) < 1 or not domain:
        return []

    first = parts[0].lower()
    last = parts[-1].lower() if len(parts) > 1 else ""
    first_initial = first[0] if first else ""

    candidates: list[str] = []

    if first and last:
        candidates.extend(
            [
                f"{first}.{last}@{domain}",
                f"{first}{last}@{domain}",
                f"{first_initial}{last}@{domain}",
                f"{first_initial}.{last}@{domain}",
                f"{last}.{first}@{domain}",
                f"{first}@{domain}",
                f"{last}@{domain}",
            ]
        )
    elif first:
        candidates.append(f"{first}@{domain}")

    # Deduplicate while preserving order and skip generic patterns
    seen: set[str] = set()
    unique: list[str] = []
    for email in candidates:
        local = email.split("@")[0]
        if email not in seen and local not in GENERIC_LOCAL_PARTS:
            seen.add(email)
            unique.append(email)

    return unique


def get_mx_host(domain: str) -> Optional[str]:
    """
    Resolve the primary MX record for a domain.

    @param domain - Email domain to look up
    @returns MX hostname or None if no records exist
    """
    try:
        records = dns.resolver.resolve(domain, "MX")
        sorted_records = sorted(records, key=lambda r: r.preference)
        return str(sorted_records[0].exchange).rstrip(".")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, Exception) as exc:
        logger.debug("MX lookup failed for %s: %s", domain, exc)
        return None


def verify_email_smtp(email: str, timeout: float = 8.0) -> bool:
    """
    Perform a silent SMTP RCPT TO check against the domain's MX server.

    Many mail servers greylist or block verification probes; a 250 response
    is treated as valid, while 550/551/553 indicate rejection.

    @param email - Candidate email address
    @param timeout - Socket timeout in seconds
    @returns True when the server accepts the recipient
    """
    domain = email.split("@")[-1]
    mx_host = get_mx_host(domain)
    if not mx_host:
        return False

    try:
        with smtplib.SMTP(timeout=timeout) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo("leadscraper.local")
            smtp.mail("verify@leadscraper.local")
            code, _ = smtp.rcpt(email)

            # 250 = accepted; some servers return 251 for forwarding
            return code in (250, 251)
    except (smtplib.SMTPException, socket.timeout, OSError) as exc:
        logger.debug("SMTP verify failed for %s via %s: %s", email, mx_host, exc)
        return False


def find_valid_email(full_name: str, domain: str) -> Optional[str]:
    """
    Try permutations in order and return the first SMTP-verified address.

    @param full_name - Decision maker name
    @param domain - Company domain
    @returns Verified email or None
    """
    for candidate in generate_email_permutations(full_name, domain):
        if verify_email_smtp(candidate):
            return candidate
    return None
