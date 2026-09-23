# 2. Do the same job with Iris

Switch Continue to **Agent** mode.

## Retrieve operational context

Ask:

> Use Context Retriever to search tickets for duplicate outbound messages
> after a downstream timeout. Return the exact ticket ID, status, root cause,
> and approved mitigation. Do not invent missing details.

Ticket search is lexical, not semantic. Keep the search terms unquoted: a
quoted query asks for an exact phrase and will return nothing.

Accept the Context Retriever search. It should find `MSG-204`.

## Turn the answer into reusable team knowledge

Ask:

> Save the MSG-204 conclusion in Agent Memory with id
> `gateway-duplicate-delivery`, owner_id `gateway-workshop`, and topic
> `duplicate-delivery`. Store this question and approved answer in LangCache:
> "How should the gateway retry a timed-out downstream submit?" Then create
> `code/msg-204-handoff.md` with the incident facts and a developer/operations
> checklist.

Review and accept each tool call and file edit.

## Prove it survives the chat

Choose **New Session**, then ask:

> Search Agent Memory for "stable message id downstream retry duplicate" with
> no owner or namespace filter. Search LangCache for "How should we retry a
> timed-out gateway submit?" Summarize what each product returned.

Unlike the baseline, the next engineer starts with the incident context and the
approved answer instead of reconstructing both from scratch.

[See the data under the hood →](/tasks/redis-insight.md)
