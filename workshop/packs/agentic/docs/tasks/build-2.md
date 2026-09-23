# Build 2: remember a reply two days later

**Target:** preserve thread state and detect a natural-language opt-out without
waiting for asynchronous extraction.

The arena thread is:

1. MT: an Acme account alert;
2. two days pass;
3. MO: “who is this?”;
4. MO: “quit texting me, I've asked twice”.

The starter's keyword regex misses step 4.

## Define durable memory

Open `agent/memory-types.yaml`. Write one-sentence extraction instructions for:

- `thread_state`: campaign id and last MT timestamp;
- `identity_confusion`: the recipient does not recognize the sender;
- `opt_out_signal`: any explicit request to stop, preserving exact phrasing.

These custom types already exist on `kind-agentic`. The YAML makes their intended
meaning reviewable beside your code.

## Implement `ingestThread`

In `agent/memory.js`:

1. replace keyword-only matching with intent detection that catches the arena phrase;
2. create `identity_confusion` when the thread includes “who is this?”;
3. preserve the exact opt-out evidence in `attributes.phrasing`;
4. keep `ownerId` scoped to the recipient;
5. keep the explicit LTM write.

The scored path writes long-term memory directly. It does not wait up to a minute
for a background extractor, so every team gets comparable latency.

Run **Run my agent** once. The `soft-opt-out` case should pass. In **Redis
Insight → ram-store**, find your `optout-...` and `thread-...` memories.

This is a detection copilot. A human and the existing compliance systems still
decide and enforce the action.

[Build attributed reuse →](/tasks/build-3.md)
