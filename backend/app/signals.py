"""Technographic and intent signal extraction from company websites."""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

# SaaS footprints: (display name, patterns matched against HTML/meta/script src)
TECH_FOOTPRINTS: list[tuple[str, list[str]]] = [
    ("Shopify", ["cdn.shopify.com", "shopify.theme", "myshopify.com", "Shopify.shop"]),
    ("Salesforce", ["salesforce.com", "force.com", "salesforce-live-agent", "pardot"]),
    ("HubSpot", ["js.hs-scripts.com", "hubspot.com", "hs-analytics", "hsforms.net"]),
    ("Stripe", ["js.stripe.com", "stripe.com/v3", "checkout.stripe.com"]),
    ("React", ["react-dom", "data-reactroot", "__NEXT_DATA__", "_reactRootContainer"]),
    ("WordPress", ["wp-content", "wp-includes", "wordpress"]),
    ("Google Analytics", ["google-analytics.com", "googletagmanager.com", "gtag("]),
    ("Intercom", ["widget.intercom.io", "intercomcdn.com"]),
    ("Segment", ["cdn.segment.com", "analytics.js"]),
    ("Mailchimp", ["chimpstatic.com", "mailchimp.com"]),
    ("Zendesk", ["static.zdassets.com", "zendesk.com/embeddable"]),
    ("Hotjar", ["static.hotjar.com", "hotjar.com"]),
]

NEWS_PATHS = ("/news", "/blog", "/newsroom", "/press", "/insights", "/articles")


def detect_tech_stack(html: str) -> list[str]:
    """
    Scan homepage head and script tags for common SaaS footprints.

    @param html - Raw homepage HTML
    @returns Deduplicated list of detected technology names
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    haystack_parts: list[str] = []

    head = soup.find("head")
    if head:
        haystack_parts.append(str(head))

    for script in soup.find_all("script"):
        src = script.get("src", "")
        if src:
            haystack_parts.append(src)
        if script.string:
            haystack_parts.append(script.string[:2000])

    for meta in soup.find_all("meta"):
        haystack_parts.append(str(meta))

    haystack = "\n".join(haystack_parts).lower()
    detected: list[str] = []

    for name, patterns in TECH_FOOTPRINTS:
        if any(pattern.lower() in haystack for pattern in patterns):
            detected.append(name)

    return detected


def extract_recent_news_title(html: str) -> Optional[str]:
    """
    Extract the most recent article title from a news/blog page.

    @param html - Raw news or blog page HTML
    @returns Article title or None
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # Prefer structured article headings
    selectors = [
        "article h1",
        "article h2",
        ".post-title",
        ".entry-title",
        ".blog-post-title",
        ".article-title",
        "[class*='post'] h2",
        "[class*='article'] h1",
        "[class*='news'] h2",
        "h1",
        "h2",
    ]

    for selector in selectors:
        for el in soup.select(selector):
            title = el.get_text(strip=True)
            if _is_valid_news_title(title):
                return title

    return None


def _is_valid_news_title(title: str) -> bool:
    """Filter out nav labels and boilerplate headings."""
    if not title or len(title) < 12 or len(title) > 200:
        return False

    lower = title.lower()
    skip = {
        "blog",
        "news",
        "latest news",
        "read more",
        "contact us",
        "about us",
        "home",
        "subscribe",
    }
    if lower in skip:
        return False

    return True
