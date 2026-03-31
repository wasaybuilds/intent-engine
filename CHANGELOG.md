# Changelog

## 1.1.0 — 2026-07-15

### Added

- **Lead detail view** — click "View" on any result to open a full drawer with
  website, contact, tech stack, recent news, icebreaker, and the complete
  3-step email sequence
- **Website column** — every lead now shows its site; businesses without one
  get a clear "No site" badge instead of being dropped from results
- **Partial leads** — companies where no named decision maker could be found
  are kept as "Owner / Team" rows instead of silently disappearing
- **In-app release notes** — new Releases page in the sidebar
- New branded favicon (target mark)

### Fixed

- Hunter.io enrichment failed with HTTP 400 on free plans (`limit=20`
  exceeded the 10-result cap) — every fallback lookup silently failed and
  scrapes returned zero leads
- Hunter contact selection now accepts named personal emails when no
  executive title is present
- Broader decision-maker title matching (General Manager, Operations
  Manager, Owner, Proprietor)

## 1.0.0 — 2026-03-31

Initial public release of **Intent Engine**:

- Niche + location Google Maps discovery (Playwright)
- LLM decision-maker extraction and 3-step email sequences
- Hunter.io / Apollo enrichment fallbacks
- Clerk auth, PostgreSQL history, Celery jobs
- CSV export, CRM webhooks, location autocomplete
