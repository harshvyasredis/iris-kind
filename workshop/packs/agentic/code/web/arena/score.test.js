import test from 'node:test';
import assert from 'node:assert/strict';

import {
  cacheIsolationPassed,
  estimatedDailyCost,
  percentile50,
  summarize,
} from './score.js';

test('summarizes accuracy and efficiency metrics', () => {
  const result = summarize([
    { passed: true, promptTokens: 100, contextTokens: 80, latencyMs: 30 },
    { passed: false, promptTokens: 50, contextTokens: 120, latencyMs: 10 },
    { passed: true, promptTokens: 25, contextTokens: 20, latencyMs: 20 },
  ]);
  assert.deepEqual(result, {
    accuracy: 67,
    promptTokens: 175,
    p50LatencyMs: 20,
    peakContextTokens: 120,
    passed: 2,
    total: 3,
  });
});

test('cross-brand hits fail the isolation gate', () => {
  assert.equal(cacheIsolationPassed(true), false);
  assert.equal(cacheIsolationPassed(false), true);
});

test('cost and p50 calculations are deterministic', () => {
  assert.equal(percentile50([8, 2, 5, 1]), 2);
  assert.equal(estimatedDailyCost(1000, 1000, 5), 5);
});
