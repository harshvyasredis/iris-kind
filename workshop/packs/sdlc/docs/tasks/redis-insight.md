# 3. See it in Redis Insight

Return to the workbench and maximize **Redis Insight**. The connections are
preconfigured; do not add a database.

Two settings make this exercise far easier:

1. Open a database, choose **Browse**, and switch the key display from the
   grouped **tree** icon to the flat **list** icon. Tree view groups keys on
   `:` and hides the part you are looking for.
2. Type the pattern below into **Filter by Key Name or Pattern** and press
   Enter. Patterns need `*` on both sides.

## Context Retriever: `cr-data`

Filter: `*MSG-204*`

Open `ticket:MSG-204`. It is a JSON document with `id`, `title`, `status`, and
`body` — exactly the fields the assistant searched. There are only four
tickets here; `ticket:*` shows them all.

This is operational context made queryable to the assistant, not copied into a
prompt by a human during an incident.

## Agent Memory: `ram-store`

Filter: `*gateway-duplicate-delivery*`

That returns one hash named like
`memory:<uuid>:ltm:gateway-duplicate-delivery`. The UUID is the memory store,
`ltm` means long-term memory, and the last segment is the id you asked the
agent to use.

Open it and read these fields:

| Field | What it holds |
|---|---|
| `text` | the reusable MSG-204 conclusion, in plain English |
| `topics` | `duplicate-delivery` |
| `memory_type` | `semantic` |
| `text_vector` | the embedding; binary, and not meant to be read |

If the filter returns nothing, the agent did not save the memory. Go back and
re-run the Agent Memory prompt.

## LangCache: `lc-cache`

Filter: `langcache:*`

Keys look like `langcache:<cache-id>:<entry-id>`, so the readable part is
inside the hash rather than in the key name. Open the newest entry and read
`prompt` and `response`: your retry question and its approved answer.
`prompt_vector` and `exact_digest` are how LangCache matches a later question.

This is why a semantically similar question in a later session can reuse a
known answer instead of paying for another model call.

## What are the other databases?

- `cr-metadata` describes Context Retriever surfaces and schemas.
- `ram-metadata` describes Agent Memory stores.
- `lc-metadata` describes LangCache caches and credentials.
- `workshop` is available to participant application code.

Do not edit or delete keys in this exercise.

[Finish with the takeaway →](/tasks/takeaway.md)
