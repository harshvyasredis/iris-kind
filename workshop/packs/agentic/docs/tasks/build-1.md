# Build 1: retrieve less, know more

**Target:** cite the right operational record while keeping each context pack
under its budget.

The seeded surface contains `Ticket`, `Runbook`, `FilterDecision`,
`CampaignCase`, and `DeliveryEvent`. Those are different questions, not five
names for “document.”

## Design the contract

Open `agent/schema.yaml`. Replace each `TODO` with:

- `text` for words people search (`title`, `body`, `steps`, `reason`);
- `tag` for exact filters (`brand`, `error_code`, `status`, `year`);
- `stored` for fields you return but do not search;
- keep identifiers as `key`.

The live surface is already provisioned to this catalog. Your YAML records the
design your `retrieve()` must honor.

## Build the context pack

Open `agent/retrieve.js`. Change it so it:

1. routes “why blocked / code” questions to `FilterDecision`;
2. routes bind recovery questions to `Runbook`;
3. otherwise searches `Ticket`;
4. extracts exact `brand`, `error_code`, and `status` filters when present;
5. requests at most three records;
6. projects only evidence the answer needs.

Do not put quotes around the search string. Context Retriever search is lexical;
a quoted phrase asks for the exact phrase and can return nothing.

Return the same shape:

```js
{ entity, citations, text, chars, latencyMs }
```

## Test it

In **App**, choose **Run retrieval cases**.

The three cases test:

- a prior Acme incident with `30007`;
- a human explanation for filter code `30007`;
- an unrelated SMPP bind failure that must not pull the Acme filter incident.

A hit inside a 12,000-character dump does not pass. Correct entity, citation,
and context budget all count.

If a case misses, use **Redis Insight → cr-data** to inspect the entity keys.
Do not edit product indexes or metadata.

[Build delayed-thread memory →](/tasks/build-2.md)
