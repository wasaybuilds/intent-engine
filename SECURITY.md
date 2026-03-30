# Security Policy

## Reporting a vulnerability

If you find a security issue in Intent Engine, please email the maintainer privately instead of opening a public issue.

Do **not** include production secrets, API keys, or personal data in reports.

## Secrets

Never commit `.env`, `.env.local`, Clerk secret keys, Hunter/Apollo keys, or LLM API keys.
Rotate any credential that may have been exposed.
