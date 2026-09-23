# Setup and naive baseline

## 1. Check the services

Open **App**. The badge should report **4/4 services ready**. If it does not,
open **Terminal** and read the Vite log before changing code.

Credentials and ClusterIP endpoints are injected into the server. Never put
`OPENAI_API_KEY`, `LC_TOKEN`, or `CR_AGENT_KEY` in browser JavaScript.

## 2. See the line you must beat

Choose **Show naive baseline**.

The reference agent:

- searches one broad entity and sends full records;
- recognizes only `STOP` and `UNSUBSCRIBE`;
- searches LangCache without a brand attribute.

It can be right by luck. It is still expensive and unsafe.

## 3. Find your files

In **Code**, expand `agent/`:

- `retrieve.js` + `schema.yaml`
- `memory.js` + `memory-types.yaml`
- `cache.js` + `cache-policy.yaml`

Only edit these files. The `arena/` directory is the test harness.

Continue is available if you want to inspect the three MCP servers. It does not
write the scored agent for you.

[Build the retriever →](/tasks/build-1.md)
