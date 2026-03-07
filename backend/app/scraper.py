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
from app.enrichment import fallback_enrich_decision_maker
from app.llm_extractor import (
    EmailSequence,
    extract_decision_makers,
    generate_email_sequence,
    pick_best_decision_maker,
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
                    if lead and lead.decision_maker_name:
                        enriched.append(lead)

                self._report(
                    "VALIDATION",
                    f"Validating emails for {len(enriched)} decision maker(s)…",
                    75,
                    companies_found=len(companies),
                    companies_processed=len(companies[: self.config.max_companies]),
                )
                validated = await self._validate_emails(enriched)

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
                    await page.wait_for_timeout(self.config.navigation_delay_ms)

                    website = await self._extract_website_from_detail(page)
                    if website:
                        results.append(
                            {
                                "company_name": name.strip(),
                                "website": self._prefer_https(website),
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
        """Pull the website link from an open Google Maps place detail panel."""
        selectors = [
            'a[data-item-id="authority"]',
            'a[aria-label*="Website"]',
            'a[href^="http"]:has-text("Website")',
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                href = await locator.get_attribute("href")
                if href and "google.com" not in href:
                    return href
        return None

    async def _fallback_discovery(self, niche: str, location: str) -> list[dict]:
        """DuckDuckGo HTML fallback when Maps blocks automated access."""
        query = f"{niche} {location} site"
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
        Fetch intent signals, extract decision makers, fallback APIs, and email sequence.

        Prefers Playwright (already launched for discovery) over raw HTTP so JS-heavy
        sites and redirect chains still yield usable about/team page text.

        @param company - Dict with company_name and website
        @returns Enriched CompanyLead
        """
        base_url = self._prefer_https(company["website"])
        parsed = urlparse(base_url)
        origin = f"https://{parsed.netloc}"
        domain = extract_domain(base_url) or parsed.netloc

        combined_text_parts: list[str] = []
        tech_stack: list[str] = []
        recent_news: Optional[str] = None
        homepage_html: Optional[str] = None

        # One browser context per company — avoid slow HTTP redirects / bot walls
        context: Optional[BrowserContext] = None
        try:
            if self._browser:
                context = await self._new_stealth_context()

            homepage_html = await self._fetch_page_html(origin, context)
            if homepage_html:
                tech_stack = detect_tech_stack(homepage_html)

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
                text = self._html_to_text(page_html)
                if len(text) > 80:
                    combined_text_parts.append(f"--- Page: {path} ---\n{text}")
        finally:
            if context:
                await context.close()

        if not combined_text_parts and homepage_html:
            combined_text_parts.append(self._html_to_text(homepage_html))

        best_name = ""
        best_title = ""
        verified_email = ""
        enrichment_source = "scrape"
        loop = asyncio.get_running_loop()

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

        if not best_name:
            return CompanyLead(
                company_name=company["company_name"],
                website=company["website"],
                tech_stack=tech_stack,
                recent_news=recent_news,
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
        )

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
            if not domain or not lead.decision_maker_name:
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

    def _format_results(self, leads: list[CompanyLead]) -> list[dict]:
        """Use pandas to normalize and deduplicate the final output."""
        if not leads:
            return []

        rows = [
            {
                "company_name": lead.company_name,
                "decision_maker_name": lead.decision_maker_name,
                "title": lead.title,
                "verified_email": lead.verified_email,
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
