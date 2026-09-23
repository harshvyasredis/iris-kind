# Iris Kind lab

Kind cluster that runs Redis Enterprise plus the public Redis Iris
charts (LangCache, Agent Memory, Redis Insight).

## Prerequisites

- Docker Desktop **engine** running, **Kubernetes disabled** (or Docker Engine on Ubuntu)
- At least **25 GiB RAM** for Docker (three 6 GiB workers + 2 GiB control plane; REC wants 4 GiB RAM / 2 CPU per node)
- `make` — on a fresh Ubuntu / Docker-in-Docker VM the apt index is empty, so:
  ```bash
  sudo apt-get update
  sudo apt-get install -y make
  ```
- Licenses and an OpenAI key (see below)

Install the rest of the CLI tools with:

```bash
make setup
```

That installs `curl`, `git`, `jq`, mikefarah `yq`, `uv`, Helm 3, `kubectl`, `kind`, and `vim` on macOS (Homebrew) and Ubuntu 20.04+. Docker is not installed; start the engine yourself. You can also run `bash scripts/setup.sh` if `make` is not on PATH yet.

Python 3.12.12 is pinned (`.python-version` and `requires-python`) and installed
by `uv`. Every `make` script runs through `uv run` and the committed `uv.lock`.

## 1. Drop secrets next to this README

Gitignored. Copy real contents, not the `*.example` files.


| File                      | Required for                                     |
| ------------------------- | ------------------------------------------------ |
| `redisenterprise.license` | Redis Enterprise cluster (10 shards)             |
| `ram.license`             | Agent Memory                                     |
| `langcache.license`       | LangCache                                        |
| `openai.key`              | embeddings, extraction, LangCache search         |
| `cr.license`              | Context Retriever (optional; skipped if missing) |




## 2. Bring it up

```bash
sudo apt-get update && sudo apt-get install -y make # Ubuntu Only
git clone https://github.com/harshvyasredis/iris-kind.git
cd iris-kind
make setup
make validate
make all
make status
```

`make all` creates Kind, the operator, a 3-node REC, eleven REDBs, LangCache,
Agent Memory, Context Retriever, default
cache/store/surface `kind-default`, Redis Insight, and the workshop workbench
(`hello` pack). First run is several minutes. A second `make all` is a no-op
unless inputs changed.

```bash
make destroy    # delete the Kind cluster, stamps, and .state keys
make logs       # latest per-step logs under logs/latest/
```



## 3. Use it

The workbench is published on the Docker host at **port 8080** by Kind itself
(`workshop.hostPort` maps to the NodePort `workshop.nodePort`), so there is no
port-forward to run and nothing to keep alive:

- workbench — `http://127.0.0.1:8080/`
- Insight — `http://127.0.0.1:8080/redisinsight/` (proxied by the workbench)

On a remote or DinD lab VM, substitute that host's address or its reverse-proxy
URL for `127.0.0.1`.

The remaining services are ClusterIP. Port-forward them only if you need direct
access:

```bash
kubectl -n langcache port-forward svc/langcache 9000:9000
kubectl -n ram port-forward svc/redis-agent-memory 9001:9000
kubectl -n rec port-forward svc/redisinsight 5540:5540
```

Packs live under `workshop/packs/`. `make all` installs `hello`. For a
facilitated session, switch packs without rebuilding Kind — SDLC first, then
the agentic arena. `make redo STEP=workshop` is required each time so the
workbench stamp is not treated as already done:

```bash
# 1. ~15-minute SDLC lab (Continue + Iris MCP)
make redo STEP=workshop
make workshop PACK=sdlc

# 2. 90-minute agentic lab (App panel coding arena)
make redo STEP=workshop
make workshop PACK=agentic
```

Reload `http://127.0.0.1:8080/` after each switch. `sdlc` and `agentic` pre-wire
Continue to Agent Memory, LangCache, and Context Retriever. `agentic` also
provisions isolated `kind-agentic` resources and requires `cr.license`. VS Code
in the workbench is the IDE.

**Insight** — workbench Insight panel, or `http://127.0.0.1:8080/redisinsight/`
(the app is mounted at `/redisinsight` so the iframe works). All eleven REDBs
are preconfigured from a mounted Secret.

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