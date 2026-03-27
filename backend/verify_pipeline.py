#!/usr/bin/env python3
"""
Automated verification suite for the intent-engine backend.

Runs isolated diagnostics for:
  A) Playwright proxy + stealth evasion
  B) Hunter.io / Apollo enrichment fallback routing
  C) LLM 3-step email sequence schema validation

Bypasses FastAPI, Celery, and the frontend entirely.

Usage (from the backend directory):
    source .venv/bin/activate
    python verify_pipeline.py              # run all tests
    python verify_pipeline.py --test a     # proxy / stealth only
    python verify_pipeline.py --test b     # fallback engine only
    python verify_pipeline.py --test c     # LLM sequence only

Requirements:
    - Dependencies installed: pip install -r requirements.txt
    - Playwright browser: playwright install chromium
    - backend/.env populated (see .env.example)

Fix proxy failures:
    - Verify PROXY_URLS or PROXY_SERVER/PROXY_USERNAME/PROXY_PASSWORD in .env
    - Test credentials with: curl -x http://user:pass@host:port https://api.ipify.org
    - Ensure your provider allows HTTPS CONNECT to ipify.org and nowsecure.nl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Load backend/.env before importing app modules (app/__init__.py also loads it)
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv

load_dotenv(BACKEND_ROOT / ".env")

from app.config import settings  # noqa: E402
from app.enrichment import FallbackContact, fallback_enrich_decision_maker  # noqa: E402
from app.llm_extractor import EmailSequence, generate_email_sequence  # noqa: E402
from app.proxy_manager import ProxyExhaustedError, ProxyRotator  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("verify_pipeline")

# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

IPIFY_URL = "https://api.ipify.org?format=json"
BOT_CHECK_URL = "https://nowsecure.nl"
DUMMY_DOMAIN = "nonexistent-test-domain-xyz.com"
NAV_TIMEOUT_MS = 30_000


def _passed(message: str) -> None:
    print(f"{GREEN}[PASSED]{RESET} {message}")


def _failed(message: str) -> None:
    print(f"{RED}[FAILED]{RESET} {message}")


def _warn(message: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {message}")


def _section(title: str) -> None:
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")


# ---------------------------------------------------------------------------
# Test A — Fingerprint & proxy leak check
# ---------------------------------------------------------------------------
async def _launch_browser_with_proxy(playwright):
    """
    Mirror scraper proxy launch: rotate on failure, raise if all proxies dead.

    @param playwright - Active async Playwright handle
    @returns Connected Chromium browser
    """
    rotator = ProxyRotator.from_settings()

    if not rotator.enabled:
        _warn("No proxy configured — browser will use your direct IP")
        return await playwright.chromium.launch(headless=True)

    last_error: Exception | None = None
    attempts = rotator.attempts_remaining()

    for _ in range(attempts):
        proxy = rotator.current()
        if not proxy:
            break
        try:
            logger.info("Attempting browser launch via proxy: %s", proxy.server)
            return await playwright.chromium.launch(
                headless=True,
                proxy=proxy.to_playwright(),
            )
        except Exception as exc:
            last_error = exc
            logger.warning("Proxy launch failed (%s): %s", proxy.server, exc)
            if rotator.rotate() is None:
                break

    hint = (
        "All configured proxies failed to connect. Check PROXY_URLS or "
        "PROXY_SERVER/PROXY_USERNAME/PROXY_PASSWORD in backend/.env. "
        "Verify credentials with: curl -x http://user:pass@host:port https://api.ipify.org"
    )
    raise ProxyExhaustedError(hint) from last_error


async def _apply_stealth(page) -> None:
    """Apply playwright-stealth when installed."""
    try:
        from playwright_stealth import stealth_async

        await stealth_async(page)
    except ImportError:
        _warn("playwright-stealth not installed — skipping stealth injection")
    except Exception as exc:
        _warn(f"Stealth injection failed (non-fatal): {exc}")


async def test_a_fingerprint_and_proxy() -> bool:
    """
    Verify proxy IP visibility and basic bot-detection evasion.

    @returns True when all sub-checks pass
    """
    _section("Test A: Fingerprint & Proxy Leak Check")

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        _failed(f"Playwright not installed: {exc}")
        return False

    all_passed = True
    browser = None

    try:
        async with async_playwright() as playwright:
            try:
                browser = await _launch_browser_with_proxy(playwright)
            except ProxyExhaustedError as exc:
                _failed(str(exc))
                return False

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            await _apply_stealth(page)

            # --- Sub-test A1: ipify proxy IP ---
            try:
                response = await page.goto(
                    IPIFY_URL,
                    wait_until="domcontentloaded",
                    timeout=NAV_TIMEOUT_MS,
                )
                body = await page.inner_text("body")
                logger.info("ipify response body: %s", body.strip())

                if response and response.ok:
                    try:
                        payload = json.loads(body.strip())
                        ip = payload.get("ip", "")
                        if ip:
                            _passed(f"ipify reachable — reported IP: {ip}")
                            if not ProxyRotator.from_settings().enabled:
                                _warn("Proxy not configured; IP above is your direct connection")
                        else:
                            _failed("ipify returned JSON but no 'ip' field")
                            all_passed = False
                    except json.JSONDecodeError:
                        _failed(f"ipify response was not valid JSON: {body[:200]}")
                        all_passed = False
                else:
                    status = response.status if response else "no response"
                    _failed(
                        f"ipify request failed (status={status}). "
                        "If using a proxy, confirm it allows HTTPS to api.ipify.org"
                    )
                    all_passed = False
            except Exception as exc:
                _failed(
                    f"ipify check timed out or errored: {exc}. "
                    "Verify proxy credentials and network connectivity."
                )
                all_passed = False

            # --- Sub-test A2: bot-detection page ---
            try:
                response = await page.goto(
                    BOT_CHECK_URL,
                    wait_until="domcontentloaded",
                    timeout=NAV_TIMEOUT_MS,
                )
                title = await page.title()
                content = (await page.content()).lower()

                blocked_markers = (
                    "access denied",
                    "blocked",
                    "captcha",
                    "please verify",
                    "bot detected",
                    "forbidden",
                )
                is_blocked = any(marker in content for marker in blocked_markers)

                if response and response.ok and not is_blocked:
                    _passed(
                        f"Bot-check page loaded (status={response.status}, title={title!r}) "
                        "— no immediate block markers detected"
                    )
                elif response and response.status in (403, 429, 503):
                    _failed(
                        f"Bot-check returned blocking status {response.status}. "
                        "Stealth/proxy may be insufficient for this target."
                    )
                    all_passed = False
                elif is_blocked:
                    _failed(
                        "Bot-check page content suggests blocking/CAPTCHA. "
                        "Try a residential proxy or update playwright-stealth."
                    )
                    all_passed = False
                else:
                    status = response.status if response else "unknown"
                    _warn(
                        f"Bot-check inconclusive (status={status}, title={title!r}). "
                        "Manual review recommended."
                    )
            except Exception as exc:
                _failed(
                    f"Bot-check navigation failed: {exc}. "
                    "Site may be down or proxy may block this destination."
                )
                all_passed = False

            await context.close()

    except Exception as exc:
        _failed(f"Unexpected Playwright error: {exc}")
        return False
    finally:
        if browser:
            await browser.close()

    return all_passed


# ---------------------------------------------------------------------------
# Test B — Fallback engine routing
# ---------------------------------------------------------------------------
def _mock_hunter_contact() -> FallbackContact:
    """Synthetic Hunter.io response for structural pipeline verification."""
    return FallbackContact(
        decision_maker_name="Jane Doe",
        title="CEO",
        verified_email="jane.doe@example.com",
        source="hunter.io",
    )


def _mock_apollo_contact() -> FallbackContact:
    """Synthetic Apollo response when Hunter mock returns None."""
    return FallbackContact(
        decision_maker_name="John Smith",
        title="Founder",
        verified_email="john@example.com",
        source="apollo.io",
    )


def test_b_fallback_engine() -> bool:
    """
    Verify enrichment fallback catches scrape failures and routes to APIs safely.

    @returns True when pipeline structure is verified without crashes
    """
    _section("Test B: Fallback Engine Mock / Live Test")

    company_name = "Unscrapable Test Co"
    all_passed = True

    # Step 1 — confirm bad domain does not crash when no APIs configured
    try:
        with patch.object(settings, "hunter_api_key", ""), patch.object(
            settings, "apollo_api_key", ""
        ):
            result = fallback_enrich_decision_maker(DUMMY_DOMAIN, company_name)
        if result is None:
            _passed(
                f"Dummy domain {DUMMY_DOMAIN!r} handled gracefully — returned None (no crash)"
            )
        else:
            _warn(f"Unexpected contact for dummy domain without API keys: {result}")
    except Exception as exc:
        _failed(f"Fallback crashed on dummy domain (no API keys): {exc}")
        return False

    has_live_keys = bool(settings.hunter_api_key or settings.apollo_api_key)

    if has_live_keys:
        # Step 2 — live API call (expected empty for fake domain, but must not crash)
        try:
            result = fallback_enrich_decision_maker(DUMMY_DOMAIN, company_name)
            if result:
                _passed(
                    f"Live fallback returned contact via {result.source}: "
                    f"{result.decision_maker_name} ({result.title})"
                )
                logger.info("enrichment_source=%s", result.source)
            else:
                _passed(
                    "Live fallback APIs called without crash — no contact for dummy domain "
                    "(expected). Pipeline routing is intact."
                )
        except Exception as exc:
            _failed(
                f"Live fallback API call crashed: {exc}. "
                "Check HUNTER_API_KEY / APOLLO_API_KEY validity and network access."
            )
            all_passed = False
    else:
        # Step 2 — mock Hunter routing
        _warn("No HUNTER_API_KEY or APOLLO_API_KEY — running mocked fallback routing test")
        try:
            with patch.object(settings, "hunter_api_key", "mock-key-for-test"), patch(
                "app.enrichment._hunter_domain_search",
                return_value=_mock_hunter_contact(),
            ):
                result = fallback_enrich_decision_maker(DUMMY_DOMAIN, company_name)

            if result and result.source == "hunter.io":
                _passed(
                    f"Mock Hunter fallback routed successfully — enrichment_source={result.source}, "
                    f"contact={result.decision_maker_name} ({result.title})"
                )
                logger.info("enrichment_source=%s email=%s", result.source, result.verified_email)
            else:
                _failed(f"Mock Hunter routing failed — got: {result}")
                all_passed = False
        except Exception as exc:
            _failed(f"Mock Hunter fallback test crashed: {exc}")
            all_passed = False

        # Step 3 — mock Apollo when Hunter returns None
        try:
            with patch.object(settings, "hunter_api_key", ""), patch.object(
                settings, "apollo_api_key", "mock-key-for-test"
            ), patch("app.enrichment._apollo_domain_search", return_value=_mock_apollo_contact()):
                result = fallback_enrich_decision_maker(DUMMY_DOMAIN, company_name)

            if result and result.source == "apollo.io":
                _passed(
                    f"Mock Apollo fallback routed successfully — enrichment_source={result.source}, "
                    f"contact={result.decision_maker_name} ({result.title})"
                )
            else:
                _failed(f"Mock Apollo routing failed — got: {result}")
                all_passed = False
        except Exception as exc:
            _failed(f"Mock Apollo fallback test crashed: {exc}")
            all_passed = False

    return all_passed


# ---------------------------------------------------------------------------
# Test C — LLM email sequence schema validation
# ---------------------------------------------------------------------------
REQUIRED_SEQUENCE_KEYS = ("email_1_initial", "email_2_followup", "email_3_breakup")


def validate_email_sequence_schema(sequence: EmailSequence) -> tuple[bool, list[str]]:
    """
    Validate that an EmailSequence matches the required 3-step schema.

    @param sequence - Generated email sequence
    @returns (is_valid, list of error messages)
    """
    errors: list[str] = []

    for key in REQUIRED_SEQUENCE_KEYS:
        value = getattr(sequence, key, "")
        if not value or not str(value).strip():
            errors.append(f"Missing or empty field: {key}")

    if sequence.email_1_initial and "Subject:" not in sequence.email_1_initial:
        errors.append("email_1_initial should contain a 'Subject:' line")

    if sequence.email_1_initial and "Body:" not in sequence.email_1_initial:
        errors.append("email_1_initial should contain a 'Body:' section")

    for key in ("email_2_followup", "email_3_breakup"):
        value = getattr(sequence, key, "")
        if value and "Body:" not in value:
            errors.append(f"{key} should be prefixed with 'Body:'")

    placeholder_pattern = re.compile(r"\[(?:Name|Company|.*?)\]|\{\{.*?\}\}")
    for key in REQUIRED_SEQUENCE_KEYS:
        value = getattr(sequence, key, "")
        if value and placeholder_pattern.search(value):
            errors.append(f"{key} contains unresolved placeholders")

    return len(errors) == 0, errors


def test_c_llm_sequence_schema() -> bool:
    """
    Generate and validate a 3-step email sequence from a mock company profile.

    @returns True when schema validation passes
    """
    _section("Test C: LLM Schema Validation Test")

    mock_profile = {
        "company_name": "SaaSify",
        "decision_maker_name": "Alex Morgan",
        "title": "CEO",
        "tech_stack": ["Stripe", "React"],
        "recent_news": "Just secured Series A funding",
        "niche": "Marketing Software",
    }

    logger.info(
        "Mock profile: company=%s niche=%s tech=%s news=%s",
        mock_profile["company_name"],
        mock_profile["niche"],
        mock_profile["tech_stack"],
        mock_profile["recent_news"],
    )

    if not settings.llm_enabled:
        _warn(
            "LLM_API_KEY not set — running template fallback sequence "
            "(schema structure still validated)"
        )

    try:
        sequence = generate_email_sequence(
            company_name=mock_profile["company_name"],
            decision_maker_name=mock_profile["decision_maker_name"],
            title=mock_profile["title"],
            tech_stack=mock_profile["tech_stack"],
            recent_news=mock_profile["recent_news"],
            niche=mock_profile["niche"],
        )
    except Exception as exc:
        _failed(
            f"LLM sequence generation crashed: {exc}. "
            "Check LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL in backend/.env"
        )
        return False

    is_valid, errors = validate_email_sequence_schema(sequence)

    print(f"\n{BOLD}--- Generated Email Sequence ---{RESET}")
    for key in REQUIRED_SEQUENCE_KEYS:
        value = getattr(sequence, key, "")
        preview = value[:500] + ("…" if len(value) > 500 else "")
        print(f"\n{key}:\n{preview}")
    if sequence.custom_icebreaker:
        print(f"\ncustom_icebreaker (snippet):\n{sequence.custom_icebreaker}")

    if is_valid:
        mode = "LLM live" if settings.llm_enabled else "template fallback"
        _passed(f"Email sequence schema valid ({mode}) — all 3 steps present and well-formed")
        return True

    for err in errors:
        _failed(err)
    return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
async def run_all(selected: Optional[str] = None) -> int:
    """
    Execute requested verification tests and return process exit code.

    @param selected - 'a', 'b', 'c', or None for all
    @returns 0 on full success, 1 on any failure
    """
    print(f"{BOLD}Intent Engine — Pipeline Verification Suite{RESET}")
    print(f"Backend root: {BACKEND_ROOT}")
    print(f"Proxy enabled: {ProxyRotator.from_settings().enabled}")
    print(f"LLM enabled:   {settings.llm_enabled}")
    print(f"Hunter key:    {'set' if settings.hunter_api_key else 'not set'}")
    print(f"Apollo key:    {'set' if settings.apollo_api_key else 'not set'}")

    results: dict[str, bool] = {}

    if selected in (None, "a"):
        results["A"] = await test_a_fingerprint_and_proxy()
    if selected in (None, "b"):
        results["B"] = test_b_fallback_engine()
    if selected in (None, "c"):
        results["C"] = test_c_llm_sequence_schema()

    _section("Summary")
    exit_code = 0
    for name, passed in results.items():
        if passed:
            _passed(f"Test {name}")
        else:
            _failed(f"Test {name}")
            exit_code = 1

    if exit_code == 0:
        print(f"\n{GREEN}{BOLD}All selected tests passed.{RESET}")
    else:
        print(f"\n{RED}{BOLD}One or more tests failed — review logs above.{RESET}")

    return exit_code


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Verify intent-engine proxy evasion, API fallbacks, and LLM sequences.",
    )
    parser.add_argument(
        "--test",
        choices=["a", "b", "c"],
        help="Run a single test (default: run all)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_all(selected=args.test)))


if __name__ == "__main__":
    main()
