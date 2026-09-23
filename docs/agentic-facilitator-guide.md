# Agentic gateway workshop facilitator guide

Run this 90-minute lab for developers and operations people who keep a messaging
gateway healthy. All records and brands are fictional. This is not Verizon
production data or architecture.

The workshop premise is narrow: the gateway already sees the reply side and the
delivery side. Participants build over that data without asking a brand to
integrate anything.

## What they should learn

1. Retrieval quality comes from entity design, exact filters, projection, and a
   context budget—not from adding a larger prompt.
2. Memory should preserve durable, reviewable state across delayed replies.
3. Cache attributes are an isolation boundary, not optional metadata.
4. Accuracy is the gate; tokens, latency, and context decide whether a correct
   agent is operationally affordable.

Do not imply the agent should operate the gateway or enforce compliance without
human review.

## Before the workshop

Confirm these files are present and non-empty:

- `redisenterprise.license`
- `ram.license`
- `langcache.license`
- `cr.license`
- `openai.key`

Bring up the environment and select the pack:

```bash
make setup
make validate
make all
make redo STEP=workshop
make workshop PACK=agentic
make status
```

Open the workbench and verify:

- App says **4/4 services ready**.
- **Show naive baseline** renders four metrics.
- **Run retrieval cases** completes (the starter is expected to miss).
- Redis Insight has `cr-data`, `ram-store`, and `lc-cache`.

The workbench is `http://127.0.0.1:8080/` on the Docker host. On a lab VM,
use its published reverse-proxy URL. No participant port-forward is required.

## 90-minute run of show

| Time | Facilitate | Participants |
|---|---|---|
| 0:00 | Explain the reply + delivery asymmetry. State the fictional-data boundary. | Open Welcome |
| 0:05 | Show the naive reference. Ask why “right by luck” is not enough. | Setup and inspect files |
| 0:10 | Introduce entity routing, tags, and context budgets. | Build 1 |
| 0:27 | Compare retrieval scores. Show one `cr-data` key. | Finish retrieval |
| 0:30 | Read the thread aloud, including the two-day gap. | Build 2 |
| 0:47 | Reinforce copilot vs compliance enforcement. | Inspect RAM |
| 0:50 | Demonstrate the cross-brand poison case. | Build 3 |
| 1:07 | Ask teams for their cache boundary before they run. | Inspect LangCache |
| 1:10 | Run the full arena together. Accuracy first, then efficiency. | Iterate once |
| 1:25 | Ask the single whiteboard question. Let the room answer first. | Propose products |

## Build 1 answer key

Gold operational records:

- `TKT-1847`: 2023 Acme incident, closed, error `30007`; a public URL
  shortener entered the simulated content-filter block list.
- `RB-30007`: preserve a sample, compare against registration, appeal, and do
  not blindly retry.
- `FD-30007`: human-readable filter explanation and registered-domain remedy.

A good schema uses:

- `text`: title, body, mitigation, steps, reason, remediation;
- `tag`: brand, error code, status, year, category;
- `key`: ids.

A passing implementation routes filter explanations to `FilterDecision`, bind
recovery to `Runbook`, and prior incidents to `Ticket`; uses unquoted lexical
terms; applies exact filters; limits to three; and projects only useful fields.

Do not reveal `TKT-1847` before they run the first case. If the whole room is
stuck after five minutes, reveal only `error_code=30007` as the filter.

## Build 2 answer key

The starter regex matches only `STOP` or `UNSUBSCRIBE`. The gold phrase is:

> quit texting me, I've asked twice

Passing code:

- recognizes that phrase as an opt-out;
- stores its exact evidence as `opt_out_signal`;
- stores “who is this?” as `identity_confusion`;
- preserves campaign id and last MT time as `thread_state`;
- scopes all memories to the recipient owner.

The arena writes LTM explicitly for deterministic timing. The provisioned store
also has custom extraction types; show asynchronous extraction only as an
optional post-lab demonstration.

## Build 3 answer key

Both set and search must carry:

```js
{ brand: context.brand, intent: context.intent, channel: context.channel }
```

The poison case stores an Acme identity answer, then asks the identical question
as Globex. A hit is a failure even if the semantic similarity is perfect.

The cost line uses a fixed $5 per one million tokens and 12 million requests/day.
It is a workshop sensitivity calculation, not Redis or OpenAI pricing.

## Arena interpretation

- **Accuracy:** five deterministic behavioral checks; this is the gate.
- **Prompt tokens:** a context-size estimate for the evaluated requests.
- **Peak context:** catches dump-all retrieval.
- **p50 latency:** measures product calls in this workshop cluster.

The naive reference is fixed so room comparisons share a baseline. Team scores
come from their live Iris calls. Do not optimize a failed answer.

## Redis Insight filters

- `cr-data`: `ticket:TKT-1847`, `runbook:RB-30007`, `filter:FD-30007`
- `ram-store`: `*optout-*`, `*thread-*`
- `lc-cache`: inspect prompt, response, and `brand` / `intent` / `channel`

Switch from tree view to list view when wildcard filtering. Do not edit product
metadata or embedding/index fields.

## If something breaks

| Symptom | Check |
|---|---|
| App is not 4/4 | Terminal Vite log; `make status`; workshop Secret |
| `/iris/*` returns 502 | product pod readiness and injected endpoint variables |
| CR finds nothing | remove query quotes; inspect entity route and tag names |
| No CR entity tool | `kind-agentic` surface provisioned before workshop install |
| RAM create rejects | custom type name and attribute field spelling |
| Soft opt-out misses | keyword regex still present |
| Cross-brand case fails | attributes must be on both set and search |
| Old cache result interferes | arena prompt includes a unique run id |

## Close

Ask only:

> What does this gateway already know that its customers would pay to be told?

Wait for the team. If needed, prompt after they answer:

- operations copilot over tickets and runbooks;
- reply understanding and identity confusion;
- natural-language opt-out detection;
- campaign approval copilot;
- human-readable blocked-traffic explanations.

Every strong first answer should live inside gateway data already flowing today.
