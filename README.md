# Iris Kind lab

A local Kind cluster that runs Redis Enterprise plus the public Redis Iris
charts (LangCache, Agent Memory, Redis Insight). It does not use Docker
Compose, Docker Desktop Kubernetes, or OSS Redis Stack.

## Prerequisites

- Docker Desktop **engine** running, **Kubernetes disabled**
- At least **25 GiB RAM** for Docker (three 6 GiB workers + 2 GiB control plane; REC wants 4 GiB RAM / 2 CPU per node)
- `kind`, `kubectl`, Helm 3, `make`, `yq`, `uv`
- Licenses and an OpenAI key (see below)

Python 3.12.12 is pinned (`.python-version` and `requires-python`) and installed
by `uv`. Every `make` script runs through `uv run` and the committed `uv.lock`.

## 1. Drop secrets next to this README

Gitignored. Copy real contents, not the `*.example` files.

| File | Required for |
|---|---|
| `redisenterprise.license` | Redis Enterprise cluster (10 shards) |
| `ram.license` | Agent Memory |
| `langcache.license` | LangCache |
| `openai.key` | embeddings, extraction, LangCache search |
| `cr.license` | Context Retriever (optional; skipped if missing) |

A bad Redis Enterprise license does not fail Helm. The cluster falls back to a
4-shard trial and databases stay `pending`. `make rec` checks that the operator
accepted the license before continuing.

## 2. Bring it up

```bash
git clone git@github.com:harshvyasredis/iris-kind.git
cd iris-kind
make validate
make all
make status
```

`make all` creates Kind, the operator, a 3-node REC, ten REDBs, LangCache,
Agent Memory, default cache/store `kind-default`, and Redis Insight. First run
is several minutes. A second `make all` is a no-op unless inputs changed.

Playbook is not installed (no public chart yet). Its two databases are created
anyway.

```bash
make destroy    # delete the Kind cluster and recorded steps
make logs       # latest per-step logs under logs/latest/
```

## 3. Use it

Services are ClusterIP. Port-forward what you need:

```bash
kubectl -n rec port-forward svc/redisinsight 5540:5540
kubectl -n langcache port-forward svc/langcache 9000:9000
kubectl -n langcache port-forward svc/langcache-controlplane 9100:9100
kubectl -n ram port-forward svc/redis-agent-memory 9001:9000
```

**Insight** — http://127.0.0.1:5540 — every REDB is already a named connection.

**LangCache** — Bearer token and cache id in `.state/langcache-default-cache.json`
(mode 0600). Data plane is port 9000.

**Agent Memory** — store `kind-default`. Do not pin a `/v1/stores/<id>/mcp` URL;
the id changes on every recreate. Add this Cursor MCP server **once**, using the
absolute path of this clone:

```json
"redis-agent-memory": {
  "command": "uv",
  "args": [
    "run",
    "--directory",
    "/absolute/path/to/iris-kind",
    "python",
    "scripts/ram_mcp.py"
  ]
}
```

`make ram-mcp` prints the snippet for this machine. After `make destroy` /
`make all`, reload MCP in Cursor; do not edit the config. That process is
long-term memory only (`create`, `search`, `edit`, `delete`).

## 4. Prove it

```bash
make test-ram          # public API, MCP, Insight, then OpenAI extraction
make test-langcache    # health/auth, then exact/semantic/TTL/flush
```

Core tests skip OpenAI. Feature tests need `openai.key`. LangCache conversational
search is skipped if the published chart returns 501.

## Versions and knobs

Pins live in `config.yaml` (operator `8.2.0-15`, LangCache `0.0.1`, Agent Memory
`0.7.0`, Insight `3.8.0`). `make pin-latest` refreshes public chart tags.

To re-run a step: `make redo STEP="rec databases"` then `make all`.
Staged targets: `make cluster operator license rec databases secrets iris insight`.
Resource ceilings, REDB sizes, and license paths are all in `config.yaml`.
