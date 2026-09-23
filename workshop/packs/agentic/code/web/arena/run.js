import { retrieve } from '../agent/retrieve.js';
import { ingestThread } from '../agent/memory.js';
import { lookup, store } from '../agent/cache.js';
import { answerWithContext } from '../agent/iris.js';
import { cacheIsolationPassed, estimatedDailyCost, summarize } from './score.js';
import gold from './gold.json';

export const naiveResult = {
  name: 'Naive reference',
  accuracy: 40,
  promptTokens: 11840,
  p50LatencyMs: 1780,
  peakContextTokens: 3240,
  cacheHitRate: 0,
  dailyCost: estimatedDailyCost(11840 / 5),
  cases: [],
};

function retrievalPassed(test, result) {
  const citations = result.citations || [];
  if (test.citation && !citations.includes(test.citation)) return false;
  if (test.forbiddenCitation && citations.includes(test.forbiddenCitation)) return false;
  if (test.entity && result.entity !== test.entity) return false;
  return result.chars <= test.maxChars;
}

export async function runRetrievalCases(onProgress = () => {}) {
  const cases = [];
  for (const test of gold.retrieval) {
    onProgress(`Retrieving: ${test.id}`);
    const started = performance.now();
    try {
      const result = await retrieve(test.question);
      const completion = await answerWithContext(test.question, result.text);
      cases.push({
        id: test.id,
        passed: retrievalPassed(test, result),
        latencyMs: performance.now() - started,
        contextTokens: Math.ceil(result.chars / 4),
        promptTokens: completion.usage?.prompt_tokens
          ?? Math.ceil((result.chars + test.question.length) / 4),
        detail: (
          `${result.entity}: ${result.citations.join(', ') || 'no citation'}; ` +
          `${completion.usage?.prompt_tokens ?? 'estimated'} prompt tokens`
        ),
      });
    } catch (error) {
      cases.push({ id: test.id, passed: false, detail: error.message });
    }
  }
  return { name: 'My retriever', ...summarize(cases), cases };
}

export async function runMine(onProgress = () => {}) {
  const retrieval = await runRetrievalCases(onProgress);
  const cases = [...retrieval.cases];
  onProgress('Testing delayed-thread memory');
  const runId = crypto.randomUUID();
  const latestReply = gold.memory.latestReply;
  const thread = {
    threadId: `thread-${runId}`,
    recipientId: `recipient-${runId}`,
    campaignId: 'cmp-acme-alerts',
    lastMtAt: '2026-09-21T14:00:00Z',
    messages: [
      { direction: 'MT', at: '2026-09-21T14:00:00Z', text: 'Acme: your account alert is ready.' },
      { direction: 'MO', at: '2026-09-23T14:00:00Z', text: 'who is this?' },
      { direction: 'MO', at: '2026-09-23T14:01:00Z', text: latestReply },
    ],
  };
  const memoryStarted = performance.now();
  try {
    const memory = await ingestThread(thread);
    cases.push({
      id: 'soft-opt-out',
      passed: memory.isOptOut === gold.memory.expectedOptOut,
      latencyMs: performance.now() - memoryStarted,
      contextTokens: Math.ceil(JSON.stringify(thread).length / 4),
      promptTokens: Math.ceil(JSON.stringify(thread).length / 4),
      detail: memory.isOptOut ? 'opt-out remembered' : 'soft opt-out missed',
    });
  } catch (error) {
    cases.push({ id: 'soft-opt-out', passed: false, detail: error.message });
  }

  onProgress('Testing cross-brand cache isolation');
  const cachePrompt = `${gold.cache.prompt} [arena ${runId}]`;
  const cacheStarted = performance.now();
  try {
    await store(cachePrompt, 'Acme account alerts. Reply STOP to opt out.', {
      brand: 'acme',
      intent: 'identity',
      channel: 'sms',
    });
    const result = await lookup(cachePrompt, {
      brand: 'globex',
      intent: 'identity',
      channel: 'sms',
    });
    cases.push({
      id: 'cache-isolation',
      passed: cacheIsolationPassed(result.hit),
      latencyMs: performance.now() - cacheStarted,
      contextTokens: Math.ceil(cachePrompt.length / 4),
      promptTokens: result.hit ? 0 : Math.ceil(cachePrompt.length / 4),
      cacheHit: result.hit,
      detail: result.hit ? 'cross-brand cache leak' : 'brand isolation held',
    });
  } catch (error) {
    cases.push({ id: 'cache-isolation', passed: false, detail: error.message });
  }

  const score = summarize(cases);
  return {
    name: 'My agent',
    ...score,
    cacheHitRate: cases.find((item) => item.id === 'cache-isolation')?.cacheHit ? 100 : 0,
    dailyCost: estimatedDailyCost(score.promptTokens / score.total),
    cases,
  };
}
