"""Async Playwright + BeautifulSoup lead discovery with LLM enrichment."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import settings
from app.email_validator import extract_domain, find_valid_email
from app.enrichment import enrich_phones_for_person, fallback_enrich_decision_maker
from app.llm_extractor import (
    EmailSequence,
    extract_decision_makers,
    generate_email_sequence,
    pick_best_decision_maker,
)
from app.phone_validator import (
    classify_phone_context,
    clean_phone_raw,
    extract_phone_candidates,
    extract_phones_near_name,
    extract_tel_hrefs,
    pick_best_phones,
)
from app.proxy_manager import ProxyExhaustedError, ProxyRotator
from app.signals import NEWS_PATHS, detect_tech_stack, extract_recent_news_title

logger = logging.getLogger(__name__)

ProgressCallback = Callable[..., None]

try:
    from playwright_stealth import stealth_async as apply_stealth
except ImportError:  # pragma: no cover - optional at install time
    apply_stealth = None

ENRICHMENT_PATHS = (
    "/about",
    "/about-us",
    "/team",
    "/our-team",
    "/leadership",
    "/management",
    "/contact",
    "/contact-us",
    "/people",
    "/staff",
)


@dataclass
class CompanyLead:
    """Intermediate representation before email validation."""

    company_name: str
    website: str
    decision_maker_name: str = ""
    title: str = ""
    verified_email: str = ""
    tech_stack: list[str] = field(default_factory=list)
    recent_news: Optional[str] = None
    custom_icebreaker: str = ""
    email_1_initial: str = ""
    email_2_followup: str = ""
    email_3_breakup: str = ""
    enrichment_source: str = "scrape"
    # Public business line (Maps / website) — dual-verified when set
    public_phone: str = ""
    # Owner / personal mobile or direct dial — dual-verified when set
    personal_phone: str = ""
    public_phone_verified: bool = False
    personal_phone_verified: bool = False
    # Raw candidates collected before dual verification
    _phone_personal_raw: list[tuple[str, str]] = field(default_factory=list)
    _phone_public_raw: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ScrapeConfig:
    """Runtime limits for a single scrape job."""

    max_companies: int = 25
    page_timeout_ms: int = 30_000
    navigation_delay_ms: int = 1_500


class LeadScraper:
    """
    Orchestrates directory discovery, intent signals, LLM enrichment, and validation.

    Playwright browser contexts use residential proxy rotation and stealth evasion.
    Browser instances are always closed in finally blocks to prevent memory leaks.
    """

    def __init__(
        self,
        config: Optional[ScrapeConfig] = None,
        on_progress: Optional[ProgressCallback] = None,
        niche: str = "",
    ) -> None:
        self.config = config or ScrapeConfig(max_companies=settings.max_companies)
        self.on_progress = on_progress
        self.niche = niche
        self._browser: Optional[Browser] = None
        self._proxy_rotator = ProxyRotator.from_settings()

    def _report(
        self,
        step: str,
        detail: str,
        percent: int,
        **extra: Any,
    ) -> None:
        """Forward progress to Celery (or any caller) when a callback is set."""
        if self.on_progress:
            self.on_progress(step, detail, percent, **extra)

    async def scrape(self, niche: str, location: str) -> list[dict]:
        """
        Run the full scrape pipeline and return cleaned lead records.

        @param niche - Business niche to search
        @param location - Geographic area
        @returns Enriched lead dicts with intent signals and email sequences
        """
        self.niche = niche

        async with async_playwright() as playwright:
            try:
                self._browser = await self._launch_browser_with_proxy(playwright)
            except ProxyExhaustedError as exc:
                logger.error("All proxies failed — aborting discovery: %s", exc)
                self._report("DISCOVERY", "Proxy connection failed — task aborted safely", 100)
                return []

            try:
                self._report("DISCOVERY", f"Searching directories for {niche} in {location}…", 10)
                companies = await self._discover_companies(niche, location)
                self._report(
                    "DISCOVERY",
                    f"Found {len(companies)} companies with websites",
                    25,
                    companies_found=len(companies),
                )

                enriched: list[CompanyLead] = []
                total = max(len(companies[: self.config.max_companies]), 1)

                for index, company in enumerate(companies[: self.config.max_companies]):
                    percent = 25 + int((index / total) * 45)
                    self._report(
                        "ENRICHMENT",
                        f"Intent signals + LLM: {company['company_name']}",
                        percent,
                        companies_found=len(companies),
                        companies_processed=index,
                    )

                    lead = await self._enrich_company(company)
                    if not lead:
                        continue

                    # Keep company rows even when no named contact was found —
                    # otherwise discovery succeeds but the UI shows zero leads.
                    if not lead.decision_maker_name:
                        lead.decision_maker_name = "Owner / Team"
                        lead.title = lead.title or "Decision Maker"
                        lead.enrichment_source = lead.enrichment_source or "partial"
                        logger.info(
                            "No named contact for %s — keeping company as partial lead",
                            company["company_name"],
                        )

                    enriched.append(lead)

                self._report(
                    "VALIDATION",
                    f"Validating emails for {len(enriched)} decision maker(s)…",
                    75,
                    companies_found=len(companies),
                    companies_processed=len(companies[: self.config.max_companies]),
                )
                validated = await self._validate_emails(enriched)

                self._report(
                    "VALIDATION",
                    f"Dual-verifying phones for {len(validated)} lead(s)…",
                    85,
                    companies_found=len(companies),
                    companies_processed=len(companies[: self.config.max_companies]),
                )
                validated = await self._validate_phones(validated)

                self._report("FORMATTING", "Cleaning and deduplicating results…", 95)
                return self._format_results(validated)
            finally:
                if self._browser:
                    await self._browser.close()
                    self._browser = None

    async def _launch_browser_with_proxy(self, playwright) -> Browser:
        """
        Launch Chromium with proxy rotation on connection failure.

        @param playwright - Active Playwright instance
        @returns Connected Browser
        @raises ProxyExhaustedError when all proxies fail
        """
        if not self._proxy_rotator.enabled:
            logger.info("No proxy configured — launching direct connection")
            return await playwright.chromium.launch(headless=True)

        last_error: Exception | None = None
        attempts = self._proxy_rotator.attempts_remaining()

        for _ in range(attempts):
            proxy = self._proxy_rotator.current()
            if not proxy:
                break

            try:
                logger.info("Launching browser via proxy %s", proxy.server)
                browser = await playwright.chromium.launch(
                    headless=True,
                    proxy=proxy.to_playwright(),
                )
                return browser
            except Exception as exc:
                last_error = exc
                logger.warning("Proxy connection failed (%s): %s", proxy.server, exc)
                if self._proxy_rotator.rotate() is None:
                    break

        raise ProxyExhaustedError(
            f"All {attempts} proxy attempt(s) failed"
        ) from last_error

    async def _apply_stealth(self, page: Page) -> None:
        """Mask headless browser fingerprints when playwright-stealth is installed."""
        if apply_stealth is not None:
            try:
                await apply_stealth(page)
            except Exception as exc:
                logger.debug("Stealth injection failed (non-fatal): %s", exc)

    async def _new_stealth_context(self) -> BrowserContext:
        """Create a browser context with realistic viewport and user agent."""
        if not self._browser:
            raise RuntimeError("Browser not initialized")

        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        return context

    async def _discover_companies(self, niche: str, location: str) -> list[dict]:
        """
        Search Google Maps via Playwright for businesses matching niche + location.

        @returns List of {company_name, website} dicts
        """
        if not self._browser:
            return []

        context = await self._new_stealth_context()
        page = await context.new_page()
        await self._apply_stealth(page)
        results: list[dict] = []

        try:
            query = f"{niche} in {location}".replace(" ", "+")
            url = f"https://www.google.com/maps/search/{query}"
            await page.goto(url, wait_until="domcontentloaded", timeout=self.config.page_timeout_ms)
            await page.wait_for_timeout(self.config.navigation_delay_ms)

            feed = page.locator('div[role="feed"]')
            if await feed.count() > 0:
                for _ in range(3):
                    await feed.evaluate("el => el.scrollTop = el.scrollHeight")
                    await page.wait_for_timeout(800)

            listings = page.locator('a[href*="/maps/place/"]')
            count = min(await listings.count(), self.config.max_companies * 2)

            seen_names: set[str] = set()
            for i in range(count):
                if len(results) >= self.config.max_companies:
                    break

                try:
                    listing = listings.nth(i)
                    name = (await listing.get_attribute("aria-label")) or ""
                    if not name or name.lower() in seen_names:
                        continue

                    seen_names.add(name.lower())
                    await listing.click()
                    # Wait for place detail panel to settle before reading Website
                    await page.wait_for_timeout(max(self.config.navigation_delay_ms, 1_800))

                    # Keep businesses without a website too — they surface as
                    # "no site" leads instead of silently disappearing
                    website = await self._extract_website_from_detail(page)
                    if not website:
                        logger.info("No website found on Maps for %s", name.strip())

                    public_phone = await self._extract_phone_from_detail(page)

                    results.append(
                        {
                            "company_name": name.strip(),
                            "website": self._prefer_https(website) if website else "",
                            "public_phone": public_phone or "",
                        }
                    )
                except Exception as exc:
                    logger.warning("Failed to parse listing %d: %s", i, exc)
                    continue
        except Exception as exc:
            logger.error("Discovery failed: %s", exc)
            self._report("DISCOVERY", "Maps blocked — using DuckDuckGo fallback…", 15)
            results = await self._fallback_discovery(niche, location)
        finally:
            await context.close()

        return results

    async def _extract_website_from_detail(self, page: Page) -> Optional[str]:
        """
        Pull the website link from an open Google Maps place detail panel.

        Maps markup changes often and many links are google.com/url redirects —
        wait for the panel, try several selectors, then unwrap redirects.
        """
        # Detail pane needs a moment after click before the Website action appears
        try:
            await page.wait_for_selector(
                'a[data-item-id="authority"], a[data-item-id*="authority"], '
                'a[aria-label*="Website" i], a[aria-label*="web site" i]',
                timeout=5_000,
            )
        except Exception:
            # Still try extraction below — panel may use a different label
            pass

        selectors = [
            'a[data-item-id="authority"]',
            'a[data-item-id*="authority"]',
            'a[aria-label*="Website" i]',
            'a[aria-label*="Web site" i]',
            'a[aria-label*="website" i]',
            'button[aria-label*="Website" i]',
            'a[data-tooltip*="Website" i]',
        ]

        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue

                href = await locator.get_attribute("href")
                aria = (await locator.get_attribute("aria-label")) or ""

                # Try href first (often a google redirect), then aria-label domain
                for candidate in (href, self._url_from_aria_label(aria)):
                    website = self._normalize_maps_website(candidate)
                    if website:
                        return website
            except Exception as exc:
                logger.debug("Website selector %s failed: %s", selector, exc)
                continue

        # Last resort: scan visible external links in the place panel
        return await self._extract_website_from_panel_links(page)

    async def _extract_phone_from_detail(self, page: Page) -> Optional[str]:
        """
        Pull the public business phone from a Google Maps place detail panel.

        Waits for the phone control (same pattern as website extraction), then
        reads data-item-id / tel: / aria-label — the three formats Maps uses.

        @param page - Maps place detail page
        @returns Raw phone string or None
        """
        try:
            await page.wait_for_selector(
                'button[data-item-id^="phone:tel:"], a[data-item-id^="phone:tel:"], '
                'a[href^="tel:"], button[aria-label*="Phone" i], a[aria-label*="Phone" i]',
                timeout=5_000,
            )
        except Exception:
            pass

        selectors = [
            'button[data-item-id^="phone:tel:"]',
            'a[data-item-id^="phone:tel:"]',
            'a[href^="tel:"]',
            'button[aria-label*="Phone" i]',
            'a[aria-label*="Phone" i]',
            'button[data-tooltip*="Copy phone" i]',
            'button[data-tooltip*="phone" i]',
        ]

        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue

                data_id = (await locator.get_attribute("data-item-id")) or ""
                href = (await locator.get_attribute("href")) or ""
                aria = (await locator.get_attribute("aria-label")) or ""
                text = (await locator.inner_text()) or ""

                # data-item-id="phone:tel:+15551234567" (most reliable Maps form)
                if "phone:tel:" in data_id:
                    return clean_phone_raw(data_id.split("phone:tel:", 1)[1])
                if href.lower().startswith("tel:"):
                    return clean_phone_raw(href)

                for blob in (aria, text):
                    # aria often looks like "Phone: (512) 555-0100"
                    candidates = extract_phone_candidates(blob)
                    if candidates:
                        return clean_phone_raw(candidates[0])
            except Exception as exc:
                logger.debug("Phone selector %s failed: %s", selector, exc)
                continue

        return None

    async def _extract_website_from_panel_links(self, page: Page) -> Optional[str]:
        """
        Scan place-detail anchors for an external business site.

        @param page - Maps place detail page
        @returns Normalized website or None
        """
        try:
            hrefs = await page.eval_on_selector_all(
                'a[href^="http"]',
                "els => els.map(el => el.getAttribute('href'))",
            )
        except Exception:
            return None

        if not isinstance(hrefs, list):
            return None

        # Prefer non-social business domains if multiple external links exist
        candidates: list[str] = []
        for href in hrefs:
            if not isinstance(href, str):
                continue
            website = self._normalize_maps_website(href)
            if website:
                candidates.append(website)

        return candidates[0] if candidates else None

    def _url_from_aria_label(self, aria_label: str) -> Optional[str]:
        """
        Extract a URL or domain from Maps aria-labels like 'Website: example.com'.

        @param aria_label - Accessibility label text
        @returns Raw URL/domain string or None
        """
        if not aria_label:
            return None

        match = re.search(
            r"(?:website|web site)\s*[:\-]?\s*(https?://[^\s]+|[a-z0-9.-]+\.[a-z]{2,})",
            aria_label,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).rstrip(".,);]")
        return None

    def _normalize_maps_website(self, href: Optional[str]) -> Optional[str]:
        """
        Convert a Maps website href into a clean company URL.

        Handles google.com/url?q= redirects and skips Maps/Google/social noise.

        @param href - Raw href or domain from the detail panel
        @returns Absolute https website or None
        """
        if not href:
            return None

        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href

        # Unwrap Google redirect wrappers: https://www.google.com/url?q=https://...
        if "google." in href and ("/url?" in href or "url?q=" in href):
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            for key in ("q", "url", "u"):
                if key in params and params[key]:
                    href = params[key][0]
                    break

        if not href.startswith("http"):
            if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}", href, re.IGNORECASE):
                href = f"https://{href}"
            else:
                return None

        parsed = urlparse(href)
        host = (parsed.netloc or "").lower().removeprefix("www.")

        # Skip non-business destinations that appear in the place panel
        blocked_hosts = (
            "google.com",
            "google.co.",
            "maps.google",
            "goo.gl",
            "g.page",
            "maps.app.goo.gl",
            "facebook.com",
            "instagram.com",
            "twitter.com",
            "x.com",
            "linkedin.com",
            "youtube.com",
            "yelp.com",
            "apple.com",
            "bing.com",
        )
        if any(host == b or host.endswith("." + b) or host.startswith(b) for b in blocked_hosts):
            return None

        if not host or "." not in host:
            return None

        return self._prefer_https(f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}".rstrip("/"))

    async def _fallback_discovery(self, niche: str, location: str) -> list[dict]:
        """DuckDuckGo HTML fallback when Maps blocks automated access."""
        query = f"{niche} {location} website"
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        companies: list[dict] = []

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            try:
                response = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; LeadScraper/1.0)"},
                )
                soup = BeautifulSoup(response.text, "lxml")

                for result in soup.select(".result")[: self.config.max_companies]:
                    title_el = result.select_one(".result__a")
                    snippet_el = result.select_one(".result__snippet")
                    if not title_el:
                        continue

                    name = title_el.get_text(strip=True)
                    href = title_el.get("href", "")
                    website = self._normalize_result_url(href)

                    if not website and snippet_el:
                        domain_match = re.search(
                            r"https?://[^\s<>\"']+",
                            snippet_el.get_text(),
                        )
                        if domain_match:
                            website = domain_match.group(0)

                    if website:
                        companies.append(
                            {
                                "company_name": name,
                                "website": self._prefer_https(website),
                            }
                        )
            except Exception as exc:
                logger.error("Fallback discovery failed: %s", exc)

        return companies

    def _prefer_https(self, url: str) -> str:
        """
        Normalize company websites to HTTPS to avoid slow HTTP→HTTPS redirects.

        @param url - Raw website URL from discovery
        @returns HTTPS URL when possible
        """
        if not url:
            return url
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http://"):
            return "https://" + url[len("http://") :]
        if not url.startswith("http"):
            return f"https://{url}"
        return url

    def _normalize_result_url(self, href: str) -> Optional[str]:
        """Convert DuckDuckGo redirect URLs to direct website links."""
        if not href:
            return None
        if href.startswith("//"):
            href = "https:" + href
        if "uddg=" in href:
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            if "uddg" in params:
                return params["uddg"][0]
        if href.startswith("http"):
            return href
        return None

    async def _enrich_company(self, company: dict) -> Optional[CompanyLead]:
        """
        Fetch intent signals, extract decision makers, phones, fallback APIs, and sequences.

        Prefers Playwright (already launched for discovery) over raw HTTP so JS-heavy
        sites and redirect chains still yield usable about/team page text.

        @param company - Dict with company_name, website, optional public_phone
        @returns Enriched CompanyLead
        """
        personal_raw: list[tuple[str, str]] = []
        public_raw: list[tuple[str, str]] = []

        maps_phone = str(company.get("public_phone") or "").strip()
        if maps_phone:
            public_raw.append((maps_phone, "google_maps"))

        # No website — keep Maps public phone and return a partial lead shell
        if not company.get("website"):
            return CompanyLead(
                company_name=company["company_name"],
                website="",
                _phone_personal_raw=personal_raw,
                _phone_public_raw=public_raw,
            )

        base_url = self._prefer_https(company["website"])
        parsed = urlparse(base_url)
        origin = f"https://{parsed.netloc}"
        domain = extract_domain(base_url) or parsed.netloc

        combined_text_parts: list[str] = []
        tech_stack: list[str] = []
        recent_news: Optional[str] = None
        homepage_html: Optional[str] = None
        scraped_html_chunks: list[str] = []

        # One browser context per company — avoid slow HTTP redirects / bot walls
        context: Optional[BrowserContext] = None
        try:
            if self._browser:
                context = await self._new_stealth_context()

            homepage_html = await self._fetch_page_html(origin, context)
            if homepage_html:
                tech_stack = detect_tech_stack(homepage_html)
                scraped_html_chunks.append(homepage_html)

            for path in NEWS_PATHS:
                news_html = await self._fetch_page_html(
                    urljoin(origin + "/", path.lstrip("/")),
                    context,
                )
                if not news_html:
                    continue
                title = extract_recent_news_title(news_html)
                if title:
                    recent_news = title
                    break

            # Cap page probes so enrichment stays fast
            for path in ENRICHMENT_PATHS[:6]:
                page_html = await self._fetch_page_html(
                    urljoin(origin + "/", path.lstrip("/")),
                    context,
                )
                if not page_html:
                    continue
                scraped_html_chunks.append(page_html)
                text = self._html_to_text(page_html)
                if len(text) > 80:
                    combined_text_parts.append(f"--- Page: {path} ---\n{text}")
        finally:
            if context:
                await context.close()

        if not combined_text_parts and homepage_html:
            combined_text_parts.append(self._html_to_text(homepage_html))

        # Collect website phones (tel: links + text) before person enrichment
        self._collect_website_phones(scraped_html_chunks, personal_raw, public_raw)

        best_name = ""
        best_title = ""
        verified_email = ""
        enrichment_source = "scrape"
        loop = asyncio.get_running_loop()
        fallback = None

        if combined_text_parts:
            candidates = await loop.run_in_executor(
                None,
                extract_decision_makers,
                "\n\n".join(combined_text_parts),
                company["company_name"],
            )
            best = pick_best_decision_maker(candidates)
            if best:
                best_name, best_title = best

        # Phones printed next to the owner's name on about/team pages
        if best_name and combined_text_parts:
            joined = "\n\n".join(combined_text_parts)
            for near in extract_phones_near_name(joined, best_name):
                personal_raw.append((near, "website_owner"))

        if not best_name:
            self._report(
                "ENRICHMENT",
                f"API fallback for {company['company_name']}…",
                0,
            )
            fallback = await loop.run_in_executor(
                None,
                fallback_enrich_decision_maker,
                domain,
                company["company_name"],
            )
            if fallback:
                best_name = fallback.decision_maker_name
                best_title = fallback.title
                verified_email = fallback.verified_email
                enrichment_source = fallback.source
                for phone in fallback.personal_phones:
                    personal_raw.append((phone, fallback.source))
                for phone in fallback.public_phones:
                    public_raw.append((phone, fallback.source))

        # When scrape found a name but no personal phone, ask Apollo/Hunter for mobiles
        if best_name and not personal_raw and domain:
            api_personal, api_public = await loop.run_in_executor(
                None,
                enrich_phones_for_person,
                domain,
                best_name,
            )
            for phone in api_personal:
                personal_raw.append((phone, "apollo.io"))
            for phone in api_public:
                public_raw.append((phone, "apollo.io"))

        if not best_name:
            return CompanyLead(
                company_name=company["company_name"],
                website=company["website"],
                tech_stack=tech_stack,
                recent_news=recent_news,
                _phone_personal_raw=personal_raw,
                _phone_public_raw=public_raw,
            )

        sequence: EmailSequence = await loop.run_in_executor(
            None,
            generate_email_sequence,
            company["company_name"],
            best_name,
            best_title,
            tech_stack,
            recent_news,
            self.niche,
        )

        return CompanyLead(
            company_name=company["company_name"],
            website=company["website"],
            decision_maker_name=best_name,
            title=best_title,
            verified_email=verified_email,
            tech_stack=tech_stack,
            recent_news=recent_news,
            custom_icebreaker=sequence.custom_icebreaker,
            email_1_initial=sequence.email_1_initial,
            email_2_followup=sequence.email_2_followup,
            email_3_breakup=sequence.email_3_breakup,
            enrichment_source=enrichment_source,
            _phone_personal_raw=personal_raw,
            _phone_public_raw=public_raw,
        )

    def _collect_website_phones(
        self,
        html_chunks: list[str],
        personal_raw: list[tuple[str, str]],
        public_raw: list[tuple[str, str]],
    ) -> None:
        """
        Harvest tel: links and phone-looking text from scraped HTML.

        Mobile/direct hints → personal candidates; everything else → public.
        """
        for html in html_chunks:
            for tel in extract_tel_hrefs(html):
                kind = classify_phone_context(tel, html[:500])
                bucket = personal_raw if kind == "personal" else public_raw
                bucket.append((tel, "website"))

            text = self._html_to_text(html)
            for candidate in extract_phone_candidates(text)[:5]:
                # Find a short window around the match for classification
                idx = text.find(candidate)
                window = text[max(0, idx - 40) : idx + len(candidate) + 40] if idx >= 0 else ""
                kind = classify_phone_context(candidate, window)
                bucket = personal_raw if kind == "personal" else public_raw
                bucket.append((candidate, "website"))

    async def _fetch_page_html(
        self,
        url: str,
        context: Optional[BrowserContext] = None,
    ) -> Optional[str]:
        """
        Load a page via Playwright when a context is available, else httpx.

        @param url - Absolute page URL
        @param context - Optional shared browser context for the company
        @returns HTML string or None on failure
        """
        if context is not None:
            page: Optional[Page] = None
            try:
                page = await context.new_page()
                await self._apply_stealth(page)
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=min(self.config.page_timeout_ms, 20_000),
                )
                if response is None or response.status >= 400:
                    return None
                await page.wait_for_timeout(300)
                return await page.content()
            except Exception as exc:
                logger.debug("Playwright fetch failed for %s: %s", url, exc)
                return None
            finally:
                if page:
                    await page.close()

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            ) as client:
                response = await client.get(url)
                if response.status_code >= 400:
                    return None
                return response.text
        except Exception as exc:
            logger.debug("HTTP fetch failed for %s: %s", url, exc)
            return None

    def _html_to_text(self, html: str) -> str:
        """Strip HTML tags and collapse whitespace for LLM/regex parsing."""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        return re.sub(r"\n{2,}", "\n", text)

    async def _validate_emails(self, leads: list[CompanyLead]) -> list[CompanyLead]:
        """Run SMTP validation in a thread pool; skip if API already provided email."""
        loop = asyncio.get_running_loop()
        validated: list[CompanyLead] = []

        for lead in leads:
            if lead.verified_email:
                validated.append(lead)
                continue

            domain = extract_domain(lead.website)
            # Skip SMTP guessing for placeholder / partial contacts
            if (
                not domain
                or not lead.decision_maker_name
                or lead.enrichment_source == "partial"
                or lead.decision_maker_name == "Owner / Team"
            ):
                validated.append(lead)
                continue

            email = await loop.run_in_executor(
                None,
                find_valid_email,
                lead.decision_maker_name,
                domain,
            )

            if email:
                lead.verified_email = email
            validated.append(lead)

        return validated

    async def _validate_phones(self, leads: list[CompanyLead]) -> list[CompanyLead]:
        """
        Dual-verify personal + public phone candidates (two independent passes).

        Only numbers that clear both passes are persisted on the lead.
        """
        loop = asyncio.get_running_loop()

        for lead in leads:
            personal, public = await loop.run_in_executor(
                None,
                pick_best_phones,
                list(lead._phone_personal_raw),
                list(lead._phone_public_raw),
            )

            if personal:
                lead.personal_phone = personal.number
                lead.personal_phone_verified = personal.verified
                logger.info(
                    "Verified personal phone for %s (%s, passes=%s, source=%s)",
                    lead.company_name,
                    personal.e164,
                    personal.verification_passes,
                    personal.source,
                )

            if public:
                lead.public_phone = public.number
                lead.public_phone_verified = public.verified
                logger.info(
                    "Verified public phone for %s (%s, passes=%s, source=%s)",
                    lead.company_name,
                    public.e164,
                    public.verification_passes,
                    public.source,
                )

        return leads

    def _format_results(self, leads: list[CompanyLead]) -> list[dict]:
        """Use pandas to normalize and deduplicate the final output."""
        if not leads:
            return []

        rows = [
            {
                "company_name": lead.company_name,
                "website": lead.website,
                "decision_maker_name": lead.decision_maker_name,
                "title": lead.title,
                "verified_email": lead.verified_email,
                "personal_phone": lead.personal_phone,
                "public_phone": lead.public_phone,
                "personal_phone_verified": lead.personal_phone_verified,
                "public_phone_verified": lead.public_phone_verified,
                "tech_stack": lead.tech_stack,
                "recent_news": lead.recent_news,
                "custom_icebreaker": lead.custom_icebreaker,
                "email_1_initial": lead.email_1_initial,
                "email_2_followup": lead.email_2_followup,
                "email_3_breakup": lead.email_3_breakup,
                "enrichment_source": lead.enrichment_source,
            }
            for lead in leads
            if lead.decision_maker_name
        ]

        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset=["company_name", "decision_maker_name"])
        df = df.sort_values(by=["company_name", "decision_maker_name"]).reset_index(drop=True)

        return df.to_dict(orient="records")
