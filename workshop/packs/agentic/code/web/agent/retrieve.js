import { searchContext } from './iris.js';

function recordsFrom(result) {
  if (Array.isArray(result)) return result;
  if (!result || typeof result !== 'object') return [];
  for (const key of ['items', 'results', 'records', 'data']) {
    if (Array.isArray(result[key])) return result[key];
  }
  return [result];
}

/**
 * Build 1: turn a gateway question into a small, cited context pack.
 *
 * This starter deliberately searches too broadly and returns full records.
 * Use schema.yaml and the workshop cases to add routing, exact filters,
 * projection, and a context budget.
 */
export async function retrieve(question) {
  // TODO: route filter explanations to FilterDecision and bind questions to Runbook.
  const entity = 'Ticket';
  // TODO: extract brand/error/status filters rather than relying on lexical luck.
  const filters = {};
  const startedAt = performance.now();
  const raw = await searchContext({
    entity,
    query: question, // Keep search terms unquoted.
    filters,
    limit: 20, // TODO: make this <= 3.
  });
  const records = recordsFrom(raw);
  const text = records.map((record) => JSON.stringify(record)).join('\n');
  const extraIds = Array.isArray(raw?.ids) ? raw.ids : [];
  const citations = [
    ...records.map((record) => record.id || record.ticket_id || record.key),
    ...extraIds,
  ]
    .map((value) => String(value || '').split(':').pop())
    .filter(Boolean);
  return {
    entity,
    citations,
    text,
    chars: text.length,
    latencyMs: performance.now() - startedAt,
  };
}
