# Contributing to Intent Engine

Thanks for helping improve this B2B lead generation tool.

## Development

1. Fork and clone the repo
2. Start Postgres + Redis with `docker compose up -d`
3. Run the FastAPI API, Celery worker, and Next.js frontend locally
4. Copy `.env.example` / `.env.local.example` and never commit secrets

## Pull requests

- Keep changes focused and describe *why* in the PR body
- Prefer small commits with clear messages
- Run `python backend/verify_pipeline.py` when touching scrape/LLM/enrichment paths
- Test auth flows if you change Clerk or API JWT handling

## Code style

- Backend: Python type hints, focused modules, JSDoc-style docstrings where helpful
- Frontend: TypeScript, existing Tailwind tokens (`ink` / `paper`), no secrets in client code
