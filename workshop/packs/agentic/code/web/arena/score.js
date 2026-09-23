export function percentile50(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) / 2)];
}

export function summarize(cases) {
  const total = cases.length || 1;
  const passed = cases.filter((item) => item.passed).length;
  return {
    accuracy: Math.round((passed / total) * 100),
    promptTokens: cases.reduce((sum, item) => sum + (item.promptTokens || 0), 0),
    p50LatencyMs: Math.round(percentile50(cases.map((item) => item.latencyMs || 0))),
    peakContextTokens: Math.max(0, ...cases.map((item) => item.contextTokens || 0)),
    passed,
    total: cases.length,
  };
}

export function estimatedDailyCost(promptTokens, requestsPerDay = 12_000_000, dollarsPerMillion = 5) {
  return (promptTokens / 1_000_000) * requestsPerDay * dollarsPerMillion;
}

export function cacheIsolationPassed(crossBrandHit) {
  return crossBrandHit === false;
}
