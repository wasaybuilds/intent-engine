# Intent Engine — B2B Lead Generation by Niche & Location

**Intent Engine** is an open-source B2B lead generation tool that scrapes Google Maps by niche and city, extracts decision makers from company websites, enriches contacts with Hunter.io/Apollo fallbacks, and generates **3-step AI cold email sequences** — with CSV export, scrape history, and CRM webhooks.

Built for sales teams, agencies, and founders doing **outbound prospecting**, **cold email**, and **local B2B lead gen** (dentists, HVAC, law firms, real estate, etc.).

---

## GitHub repo setup (copy & paste)

**Repo name:** `intent-engine`

**Description** (GitHub → Settings → About):

```
Intent Engine — open-source B2B lead scraper: find decision makers by niche & location, AI email sequences, Hunter.io fallback, CSV export & webhooks.
```

**Topics** (add under About → Topics):

```
intent-engine
b2b-leads
lead-generation
lead-scraper
web-scraping
playwright
cold-email
sales-prospecting
decision-maker
outreach-automation
fastapi
nextjs
celery
llm
hunter-io
google-maps-scraper
```

---

## What it does

1. **Search** — Enter a business niche + location (city autocomplete via OpenStreetMap).
2. **Discover** — Playwright scrapes Google Maps for matching businesses with websites.
3. **Enrich** — LLM (Groq/OpenAI-compatible) extracts CEO/founder names, titles, tech stack, and recent news from `/about`, `/team`, and similar pages.
4. **Fallback** — Hunter.io → Apollo when scraping finds no decision maker.
5. **Outreach** — AI generates a 3-step email sequence (initial, follow-up, breakup) plus a one-line icebreaker.
6. **Export** — Download leads as CSV or POST to a CRM webhook (Zapier, Make, etc.).
7. **History** — Authenticated users save past scrape jobs in PostgreSQL.

---

## Features

| Feature | Details |
|---------|---------|
| **Niche + location search** | Google Maps discovery via Playwright |
| **Decision maker extraction** | LLM + regex fallback from public team/about pages |
| **Intent signals** | Tech stack detection, recent news/blog titles |
| **Email validation** | SMTP checks on discovered addresses |
| **API enrichment** | Hunter.io and Apollo.io domain search fallbacks |
| **AI email sequences** | 3-step personalized cold outreach (Groq, OpenAI, etc.) |
| **Proxy rotation** | Residential proxy support with stealth evasion |
| **Background jobs** | Celery + Redis — scrape without blocking the UI |
| **Auth** | Clerk sign-in, JWT-protected API, per-user history |
| **CRM webhooks** | Auto-deliver completed leads to your stack |

---

## Tech stack

| Layer | Tools |
|-------|-------|
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, Clerk |
| **Backend** | FastAPI, Celery, Redis, SQLAlchemy |
| **Database** | PostgreSQL |
| **Scraping** | Playwright, playwright-stealth, BeautifulSoup |
| **AI** | Groq / OpenAI-compatible LLM API |
| **Enrichment** | Hunter.io, Apollo.io (optional) |
| **Deploy** | Docker Compose (Postgres, Redis, API, worker, frontend) |

---

## Quick start

### Prerequisites

- Python **3.11 – 3.13**
- Node.js **20+**
- Docker (Postgres + Redis)
- [Clerk](https://clerk.com/) account (free tier)
- Optional: LLM API key (Groq, OpenAI), Hunter.io / Apollo keys

### 1. Clone & start infrastructure

```bash
git clone https://github.com/YOUR_USERNAME/intent-engine.git
cd intent-engine
docker compose up -d
```

### 2. Backend

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Edit .env — see Environment variables below
```

**Terminal A — API:**

```bash
uvicorn app.main:app --reload --port 8000
```

**Terminal B — Celery worker:**

```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Add Clerk keys from dashboard.clerk.com
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — sign in, run a scrape, export CSV.

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis URL (default `redis://localhost:6379/0`) |
| `CLERK_JWKS_URL` | Yes* | Clerk JWKS endpoint |
| `CLERK_ISSUER` | Yes* | Clerk JWT issuer URL |
| `AUTH_DISABLED` | No | Set `true` to skip JWT in local dev |
| `LLM_API_KEY` | No | Groq/OpenAI key for AI extraction & emails |
| `LLM_BASE_URL` | No | Default OpenAI-compatible endpoint |
| `LLM_MODEL` | No | Model id (e.g. `llama-3.3-70b-versatile`) |
| `HUNTER_API_KEY` | No | Hunter.io domain search fallback |
| `APOLLO_API_KEY` | No | Apollo people search fallback |
| `PROXY_URLS` | No | Comma-separated residential proxy URLs |

\* Not required when `AUTH_DISABLED=true`

### Frontend (`frontend/.env.local`)

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key |
| `NEXT_PUBLIC_API_URL` | Backend URL (default `http://localhost:8000`) |

**Never commit `.env` or `.env.local`.** Use the `.example` files only.

---

## Clerk setup

1. Create an app at [dashboard.clerk.com](https://dashboard.clerk.com)
2. Copy keys into `frontend/.env.local`
3. Set backend JWT verification:
   - `CLERK_JWKS_URL` = `https://<your-clerk-domain>/.well-known/jwks.json`
   - `CLERK_ISSUER` = `https://<your-clerk-domain>`

---

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| POST | `/api/scrape` | Yes | Enqueue scrape job |
| GET | `/api/tasks/{task_id}` | Yes | Poll job progress |
| GET | `/api/history` | Yes | List past jobs |
| GET | `/api/history/{job_id}` | Yes | Job detail + leads |
| POST | `/api/webhooks/configure` | Yes | Save CRM webhook URL |

Authenticated routes require `Authorization: Bearer <clerk_jwt>`.

---

## Production (Docker)

```bash
export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
export CLERK_SECRET_KEY=sk_live_...

docker compose -f docker-compose.prod.yml up --build -d
```

Services: **postgres**, **redis**, **api**, **celery-worker**, **frontend**

---

## Project structure

```
intent-engine/
├── docker-compose.yml           # Local Postgres + Redis
├── docker-compose.prod.yml      # Full production stack
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI routes
│   │   ├── scraper.py           # Playwright discovery + enrichment
│   │   ├── llm_extractor.py     # AI decision makers + email sequences
│   │   ├── enrichment.py        # Hunter.io / Apollo fallback
│   │   ├── proxy_manager.py     # Residential proxy rotation
│   │   ├── tasks.py             # Celery scrape jobs
│   │   └── auth.py              # Clerk JWT verification
│   └── verify_pipeline.py       # Standalone pipeline tests
└── frontend/
    └── src/
        ├── app/                 # Next.js App Router
        ├── components/          # Dashboard, history, location autocomplete
        └── middleware.ts        # Clerk route protection
```

---

## Verification

Run pipeline tests without the full UI:

```bash
cd backend
source .venv/bin/activate
python verify_pipeline.py              # all tests
python verify_pipeline.py --test c     # LLM email sequence only
```

---

## Who is this for?

- **Agencies** selling websites, automations, AI chat, or AI voice to local businesses
- **SDRs / founders** building niche outbound lists (dentists, HVAC, lawyers, etc.)
- **Developers** who want a self-hosted alternative to expensive lead databases

---

## Disclaimer

This tool scrapes **publicly available** business information. You are responsible for complying with applicable laws (CAN-SPAM, GDPR, etc.) and the terms of service of data sources you use. Use ethically — verify contacts and respect opt-outs.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Keywords

B2B lead scraper · Intent Engine · lead generation · decision maker finder · Google Maps scraper · cold email tool · sales prospecting · Playwright scraping · AI outreach · Hunter.io · Apollo enrichment · FastAPI · Next.js · Celery · open source CRM leads
