"""Residential proxy rotation for Playwright browser launches."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)


class ProxyExhaustedError(Exception):
    """Raised when all configured proxies fail to connect."""


@dataclass
class ProxyConfig:
    """Playwright-compatible proxy credentials."""

    server: str
    username: Optional[str] = None
    password: Optional[str] = None

    def to_playwright(self) -> dict[str, str]:
        """
        Convert to Playwright launch/context proxy dict.

        @returns Dict with server, username, password keys
        """
        payload: dict[str, str] = {"server": self.server}
        if self.username:
            payload["username"] = self.username
        if self.password:
            payload["password"] = self.password
        return payload


class ProxyRotator:
    """
    Rotate through residential proxies on connection failure.

    Proxies are loaded from PROXY_URLS (comma-separated) or a single
    PROXY_SERVER + PROXY_USERNAME + PROXY_PASSWORD triplet.
    """

    def __init__(self, proxies: list[ProxyConfig]) -> None:
        self.proxies = proxies
        self._index = 0

    @classmethod
    def from_settings(cls) -> "ProxyRotator":
        """Build rotator from environment variables."""
        proxies: list[ProxyConfig] = []

        if settings.proxy_urls:
            for raw in settings.proxy_urls:
                parsed = parse_proxy_url(raw)
                if parsed:
                    proxies.append(parsed)
        elif settings.proxy_server:
            proxies.append(
                ProxyConfig(
                    server=settings.proxy_server,
                    username=settings.proxy_username or None,
                    password=settings.proxy_password or None,
                )
            )

        return cls(proxies)

    @property
    def enabled(self) -> bool:
        """True when at least one proxy is configured."""
        return len(self.proxies) > 0

    def current(self) -> Optional[ProxyConfig]:
        """Return the active proxy, or None when proxies are disabled."""
        if not self.proxies:
            return None
        return self.proxies[self._index]

    def rotate(self) -> Optional[ProxyConfig]:
        """
        Advance to the next proxy after a failure.

        @returns Next proxy or None when the list is exhausted
        """
        if not self.proxies:
            return None

        self._index += 1
        if self._index >= len(self.proxies):
            return None
        logger.info("Rotating to proxy %d/%d", self._index + 1, len(self.proxies))
        return self.proxies[self._index]

    def attempts_remaining(self) -> int:
        """Number of proxy attempts left including the current one."""
        if not self.proxies:
            return 1
        return len(self.proxies) - self._index


def parse_proxy_url(raw: str) -> Optional[ProxyConfig]:
    """
    Parse a proxy URL like http://user:pass@host:port into ProxyConfig.

    @param raw - Proxy URL string
    @returns ProxyConfig or None if invalid
    """
    raw = raw.strip()
    if not raw:
        return None

    if "://" not in raw:
        raw = f"http://{raw}"

    parsed = urlparse(raw)
    if not parsed.hostname or not parsed.port:
        logger.warning("Invalid proxy URL (missing host/port): %s", raw)
        return None

    scheme = parsed.scheme or "http"
    server = f"{scheme}://{parsed.hostname}:{parsed.port}"

    return ProxyConfig(
        server=server,
        username=parsed.username or None,
        password=parsed.password or None,
    )
