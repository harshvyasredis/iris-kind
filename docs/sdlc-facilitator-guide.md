# SDLC workshop facilitator guide

Run this session for developers and operations people who keep a messaging
gateway healthy. The lab is a **fictional, representative** carrier scenario.
It is not Verizon production data or architecture.

Participant docs live in the workbench left pane (`sdlc` pack). This file is
for the person running the room.

**Length:** about 15 minutes of hands-on, plus 5 minutes of setup and 5 minutes
of close. Budget **30 minutes** including questions.

## What they should feel

1. Today's coding assistant sounds confident and still starts empty.
2. Iris can retrieve the incident, keep the decision, and reuse the answer.
3. Redis Insight shows that those results live in real databases, not chat.

Do not imply the assistant should operate the gateway unsupervised.

## Night before

1. Confirm licenses next to the repo README: `redisenterprise.license`,
   `ram.license`, `langcache.license`, `openai.key`, and `cr.license`.
   Context Retriever is required for this pack's ticket search.
2. Bring the lab up:

   ```bash
   # Ubuntu / DinD only, if make is missing:
   sudo apt-get update && sudo apt-get install -y make

   make setup
   make validate
   make all
   make status
   ```

3. Confirm completed steps include `workshop`, `iris-context-retriever`,
   `cr-surface`, `iris-ram`, `iris-langcache`, and `insight`.
4. Open the workbench yourself and click through Welcome → Setup so Continue
   lists Agent Memory, LangCache, and Context Retriever tools.

### URLs

On the Docker host:

- Workbench: `http://127.0.0.1:8080/`
- Redis Insight: `http://127.0.0.1:8080/redisinsight/`

On a Redis Labs / DinD VM, use the published host port, for example:

- `https://8080-p-dind-host-dot-<lab>.labs.ps-redis.com/`
- Insight: the same origin plus `/redisinsight/`

Kind already publishes host port **8080**. Do not ask participants to
port-forward.

## Day of: 30-minute run of show

| Time | You do | They do |
|---|---|---|
| 0:00 | Share the workbench URL. Say this is a fictional gateway incident, not production. | Open the workbench |
| 0:03 | Point at **Two-minute setup**. Stay in **Chat** for the first exercise. | gpt-4o, Chat mode |
| 0:05 | Run **1. Feel the pain**. Do not paste tickets or logs for them. | Baseline prompts |
| 0:12 | Switch them to **Agent** mode. Tell them to **Accept** tool calls they understand. | Iris prompts |
| 0:22 | Maximize **Redis Insight**. Walk `cr-data` → `ram-store` → `lc-cache`. | Browser keys |
| 0:28 | Read the takeaway out loud. Stop on the “incident-responder costume” line. | Questions |

If the room is large, keep everyone on the same prompt at the same time. The
pain only lands if they see Chat fail *before* Agent mode.

## Exercise 1 — baseline (Chat mode)

Ask them to stay in Continue **Chat**. Exact prompts are in
`docs/tasks/baseline.md` in the workbench.

Expected outcome:

- Polished retry advice with **no ticket ID**.
- After **New Session**, no memory of the mitigation.

If someone “wins” by inventing `MSG-204`, call it out: guessing is not
retrieval. Ask them how they would prove it to on-call.

Talking point: *that is autocomplete wearing an incident-responder costume.*

## Exercise 2 — Iris (Agent mode)

Exact prompts are in `docs/tasks/iris-workflow.md`.

Answer key for `MSG-204`:

| Field | Expected |
|---|---|
| ID | `MSG-204` |
| Title | Duplicate outbound messages after downstream timeout |
| Status | closed |
| Root cause | Retry used a **new transaction id**; the carrier accepted both sends |
| Mitigation | Reuse the **stable message id** as the idempotency key; check delivery status before retry |

What should happen:

1. Context Retriever search finds `MSG-204`. They accept the tool call.
2. Agent Memory stores id `gateway-duplicate-delivery` (owner
   `gateway-workshop`, topic `duplicate-delivery`).
3. LangCache stores the retry Q&A.
4. Continue writes `code/msg-204-handoff.md`.
5. **New Session** still finds the memory and the cached answer.

If a tool is missing, they skipped Agent mode or Continue did not load MCP.
Have them re-run the setup prompt: *List your MCP tools. Group them by Agent
Memory, LangCache, and Context Retriever.*

## Exercise 3 — Redis Insight

Do not add databases. Connections are preconfigured.

Tell them to switch Browse from **tree** view to **list** view first. Tree view
groups keys on `:` and hides the segment they are hunting for — this is the
single most common source of confusion in this exercise.

| Alias | Filter | What to open |
|---|---|---|
| `cr-data` | `*MSG-204*` | `ticket:MSG-204`, a JSON doc with the ticket fields |
| `ram-store` | `*gateway-duplicate-delivery*` | hash `memory:<uuid>:ltm:gateway-duplicate-delivery`; read the `text` field |
| `lc-cache` | `langcache:*` | hash `langcache:<cache-id>:<entry-id>`; read `prompt` and `response` |

The memory id is the **last** key segment, and the leading UUID is the store,
so it differs every run. Always filter by pattern, never by a full key.
`text_vector` and `prompt_vector` are embeddings and look like binary garbage;
say so before someone asks.

Leave metadata DBs (`cr-metadata`, `ram-metadata`, `lc-metadata`) as “do not
edit.” `workshop` is the participant app database, not Iris product data.

## Close

Three sentences are enough:

1. Without Iris, every new chat reconstructs context the org already has.
2. With Iris, retrieve → remember → reuse, then inspect it in Redis.
3. Humans still approve mitigations; the assistant should not run the gateway.

Send them out through **Takeaway**.

## If something breaks

| Symptom | First check |
|---|---|
| Workbench blank | `make status`; workshop pod `4/4 Running`; URL uses port 8080 |
| Insight empty / extra DBs | Use the workbench `/redisinsight/` path; do not add connections |
| Continue asks for an API key | Ignore the provider card; `openai.key` is already mounted |
| No Context Retriever tools | `cr.license` present? `make redo STEP="cr-surface workshop"` then `make cr-surface && make workshop PACK=sdlc` |
| Search misses `MSG-204` | Almost always a **quoted** query. Ticket search is lexical, and a double-quoted query means exact phrase, which matches nothing. Re-ask with unquoted terms. Otherwise re-seed as above; seed lives in `scripts/cr_api.py` |
| Pack still looks like `hello` | `make redo STEP=workshop && make workshop PACK=sdlc` |
| File write denied in VS Code | Workshop init should `chown` `/work`; redo the workshop step |
| Remote lab cannot open 8080 | Confirm Kind hostPort mapping and the lab reverse-proxy pattern `<port>-p-<container>-dot-<machine>` |

Destroy and rebuild only if the cluster itself is sick:

```bash
make destroy
make all
make redo STEP=workshop
make workshop PACK=sdlc
```

That is several minutes. Prefer targeted `make redo` first.

## What not to do in the room

- Do not paste `MSG-204` during the baseline.
- Do not let Agent mode start until Chat has failed in public.
- Do not browse metadata keys as if they were the product demo.
- Do not claim this is Verizon’s real gateway.
- Do not port-forward `svc/workshop` unless Kind hostPort 8080 is genuinely
  unpublished on that host.
