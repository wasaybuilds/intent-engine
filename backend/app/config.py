"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os


class Settings:
    """
    Application settings for Redis, Celery, LLM, auth, and database.

    Environment variables:
      REDIS_URL              - Redis broker/backend URL
      DATABASE_URL           - PostgreSQL connection string
      CLERK_JWKS_URL         - Clerk JWKS endpoint for JWT verification
      CLERK_ISSUER           - Expected JWT issuer (e.g. https://xxx.clerk.accounts.dev)
      AUTH_DISABLED          - Set to "true" to skip JWT checks in local dev
      LLM_API_KEY            - OpenAI-compatible API key
      LLM_BASE_URL           - LLM API base URL
      LLM_MODEL              - Model id
      MAX_COMPANIES          - Cap companies per scrape job
      PROXY_URLS             - Comma-separated proxy URLs (user:pass@host:port)
      PROXY_SERVER           - Single proxy server URL (alternative to PROXY_URLS)
      PROXY_USERNAME         - Proxy auth username
      PROXY_PASSWORD         - Proxy auth password
      HUNTER_API_KEY         - Hunter.io domain search API key
      APOLLO_API_KEY         - Apollo.io people search API key
      NUMVERIFY_API_KEY      - Optional Numverify key for phone pass-2 carrier check
    """

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/intent_engine",
    )
    clerk_jwks_url: str = os.getenv("CLERK_JWKS_URL", "")
    clerk_issuer: str = os.getenv("CLERK_ISSUER", "").rstrip("/")
    auth_disabled: bool = os.getenv("AUTH_DISABLED", "false").lower() == "true"
    llm_api_key: str = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    max_companies: int = int(os.getenv("MAX_COMPANIES", "25"))
    proxy_urls: list[str] = [
        url.strip()
        for url in os.getenv("PROXY_URLS", "").split(",")
        if url.strip()
    ]
    proxy_server: str = os.getenv("PROXY_SERVER", "").strip()
    proxy_username: str = os.getenv("PROXY_USERNAME", "").strip()
    proxy_password: str = os.getenv("PROXY_PASSWORD", "").strip()
    hunter_api_key: str = os.getenv("HUNTER_API_KEY", "").strip()
    apollo_api_key: str = os.getenv("APOLLO_API_KEY", "").strip()
    numverify_api_key: str = os.getenv("NUMVERIFY_API_KEY", "").strip()
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]

    @property
    def llm_enabled(self) -> bool:
        """True when an API key is configured for LLM extraction."""
        return bool(self.llm_api_key.strip())

    @property
    def auth_enabled(self) -> bool:
        """True when JWT verification is required."""
        return not self.auth_disabled


settings = Settings()
