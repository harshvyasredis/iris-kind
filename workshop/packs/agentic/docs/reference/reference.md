# Data and endpoints

## Seeded Context Retriever entities

- `Ticket`: incident, brand, code, status, year, mitigation
- `Runbook`: code and approved response steps
- `FilterDecision`: code, reason, remediation
- `CampaignCase`: approval outcome and rationale
- `DeliveryEvent`: simulated MO/MT aggregate

## Server-only environment

- `RAM_URL` / `RAM_STORE_ID` → `kind-agentic`
- `LC_URL` / `LC_TOKEN` / `LC_CACHE_ID` → `kind-agentic`
- `CR_MCP_URL` / `CR_AGENT_KEY` → `kind-agentic`
- `OPENAI_API_KEY`

The Vite server exposes narrow `/app/iris/*` routes. Secrets never enter browser
source.

## Redis Insight

- `cr-data` — entity records
- `ram-store` — workshop long-term memories
- `lc-cache` — attributed cache entries
- `workshop` — app-owned data

Metadata databases, indexes, and embeddings are inspect-only.
