import { agentMemory } from './iris.js';

function safeId(value) {
  return value.toLowerCase().replace(/[^a-z0-9-]+/g, '-').slice(0, 48);
}

/**
 * Build 2: persist durable facts from a delayed reply thread.
 *
 * The starter reproduces a keyword-only gateway: it recognizes STOP but
 * misses natural-language opt-outs. Add structured opt_out_signal,
 * identity_confusion, and thread_state memories using memory-types.yaml.
 */
export async function ingestThread(thread) {
  const latest = thread.messages.at(-1);
  const isOptOut = /\b(stop|unsubscribe)\b/i.test(latest.text);
  const memories = [
    {
      id: `thread-${safeId(thread.threadId)}`,
      text: `Campaign ${thread.campaignId}; last outbound ${thread.lastMtAt}`,
      ownerId: thread.recipientId,
      memoryType: 'thread_state',
      topics: ['gateway-workshop', 'thread-state'],
      attributes: {
        campaign_id: thread.campaignId,
        last_mt_at: thread.lastMtAt,
      },
    },
  ];
  if (isOptOut) {
    memories.push({
      id: `optout-${safeId(thread.threadId)}`,
      text: latest.text,
      ownerId: thread.recipientId,
      memoryType: 'opt_out_signal',
      topics: ['gateway-workshop', 'opt-out'],
      attributes: { phrasing: latest.text, legal_risk: 'review-required' },
    });
  }
  // TODO: remember "who is this?" and natural-language requests to stop.
  await agentMemory.request('long-term-memory', { memories });
  return { isOptOut, memories };
}

export async function recall(ownerId, text = 'gateway reply state') {
  return agentMemory.request('long-term-memory/search', {
    text,
    filter: { ownerId: { eq: ownerId } },
    filterOp: 'all',
    limit: 10,
  });
}
