# Iris Kind lab

A local Kind cluster that runs Redis Enterprise plus the public Redis Iris
charts (LangCache, Agent Memory, Redis Insight). It does not use Docker
Compose, Docker Desktop Kubernetes, or OSS Redis Stack.

## Prerequisites

- Docker Desktop **engine** running, **Kubernetes disabled** (or Docker Engine on Ubuntu)
- At least **25 GiB RAM** for Docker (three 6 GiB workers + 2 GiB control plane; REC wants 4 GiB RAM / 2 CPU per node)
- `make` (on Ubuntu: `sudo apt-get install -y make`)
- Licenses and an OpenAI key (see below)

Install the rest of the CLI tools with:

```bash
make setup
```

That installs `curl`, `git`, `jq`, mikefarah `yq`, `uv`, Helm 3, `kubectl`, and `kind` on macOS (Homebrew) and Ubuntu 20.04+. Docker is not installed; start the engine yourself. You can also run `bash scripts/setup.sh` if `make` is not on PATH yet.

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
make setup
make validate
make all
make status
```

`make all` creates Kind, the operator, a 3-node REC, eleven REDBs, LangCache,
Agent Memory, Context Retriever (when `cr.license` is present), default
cache/store/surface `kind-default`, Redis Insight, and the workshop workbench
(`hello` pack). First run is several minutes. A second `make all` is a no-op
unless inputs changed.

Playbook is not installed (no public chart yet). Its two databases are created
anyway.

```bash
make destroy    # delete the Kind cluster, stamps, and .state keys
make logs       # latest per-step logs under logs/latest/
```

## 3. Use it

Services are ClusterIP. Port-forward what you need:

```bash
kubectl -n workshop port-forward svc/workshop 8080:80
kubectl -n rec port-forward svc/redisinsight 5540:5540
kubectl -n langcache port-forward svc/langcache 9000:9000
kubectl -n ram port-forward svc/redis-agent-memory 9001:9000
```

The workbench chrome is adapted from
[redis-developer/workshop-docker-template](https://github.com/redis-developer/workshop-docker-template)
(docs, VS Code, app, terminal, path-based nginx). Redis is Enterprise on this
Kind cluster; Insight is the instance already in `rec`.

Packs live under `workshop/packs/`. Default is `hello`. Switch without
rebuilding Kind:

```bash
make redo STEP=workshop
make workshop PACK=sdlc
```

`sdlc` and `agentic` pre-wire Continue MCP to Agent Memory, LangCache, and
Context Retriever (if `cr.license` is present). VS Code in the workbench is
the IDE.

**Insight** — workbench Insight panel, or
`http://127.0.0.1:5540/redisinsight/` after port-forward (the app is mounted
at `/redisinsight` so the iframe works).

**LangCache** — Bearer token and cache id in `.state/langcache-default-cache.json`
(mode 0600).

**Agent Memory** — store `kind-default`. Workshop Continue talks to it
in-cluster. Maintainers on this laptop can still run `make ram-mcp` for a
host-side stdio proxy; that is not a participant step.

**Context Retriever** — surface `kind-default` (Ticket schema + seed records)
and an agent key in `.state/context-retriever-default-surface.json` (mode 0600).
Skipped when `cr.license` is missing.

## 4. Prove it

```bash
make test-ram          # public API, MCP, Insight, then OpenAI extraction
make test-langcache    # health/auth, then exact/semantic/TTL/flush
make test-cr           # surface/schema/auth, then MCP search
```

Core tests skip OpenAI. Feature tests need `openai.key`. LangCache conversational
search is skipped if the published chart returns 501.

## Versions and knobs

Pins live in `config.yaml` (operator `8.2.0-15`, LangCache `0.0.1`, Agent Memory
`0.7.0`, Context Retriever `0.4.2`, Insight `3.8.0`). `make pin-latest` refreshes
public chart tags.

To re-run a step: `make redo STEP="rec databases"` then `make all`.
Staged targets: `make cluster operator license rec databases secrets iris insight workshop`.
Resource ceilings, REDB sizes, and license paths are all in `config.yaml`.
