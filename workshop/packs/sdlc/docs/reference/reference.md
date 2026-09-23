# Iris endpoints

Injected into the VS Code container (values are not printed in docs):

- `REDIS_URL` — `workshop` REDB
- `RAM_URL` / `RAM_STORE_ID` — Agent Memory data plane
- `LC_URL` / `LC_TOKEN` / `LC_CACHE_ID` — LangCache data plane
- `CR_MCP_URL` — Context Retriever MCP, when licensed
- `OPENAI_API_KEY` — Continue chat model

## Redis Insight aliases

- `cr-data` — Context Retriever ticket records
- `cr-metadata` — Context Retriever surface metadata
- `ram-store` — Agent Memory long-term memories
- `ram-metadata` — Agent Memory store metadata
- `lc-cache` — LangCache entries and indexes
- `lc-metadata` — LangCache cache metadata
- `workshop` — participant application data

Product metadata, indexes, and embeddings are implementation details. Inspect
them during the workshop, but do not edit them.
