# Build 3: reuse without leaking

**Target:** get semantic reuse while guaranteeing brand isolation.

The `kind-agentic` cache accepts exactly three attributes:

- `brand`
- `intent`
- `channel`

The starter omits all three. If Acme stores “Who is this?”, Globex can receive
Acme's answer.

## Write the policy

In `agent/cache-policy.yaml`, replace each `TODO` with a short reason the
attribute belongs in the cache boundary. Keep the 0.82 threshold and 24-hour TTL
for this exercise.

## Implement the boundary

In `agent/cache.js`, make `pickAttributes(context)` return only:

```js
{
  brand: context.brand,
  intent: context.intent,
  channel: context.channel
}
```

Pass that object in **both** `lookup()` and `store()`. Filtering only reads or
only writes is not isolation.

Run **Run my agent**. `cache-isolation` passes only when a Globex lookup misses
the otherwise-identical Acme entry.

Then inspect **Redis Insight → lc-cache**. Compare prompt, response, and
attributes. Embeddings and indexes are implementation detail; do not edit them.

The App extrapolates the run's prompt tokens to 12 million requests/day with a
fixed workshop rate. It is deliberately not a pricing quote. The useful move is
changing hit rate and token volume, then doing your own volume math.

[Enter the arena →](/tasks/arena.md)
