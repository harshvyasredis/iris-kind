import { langCache } from './iris.js';

/**
 * Build 3: isolate reusable answers by brand, intent, and channel.
 *
 * This starter intentionally omits attributes. It may get a hit, but it can
 * return Acme's identity answer to Globex. Fix both lookup and store.
 */
export async function lookup(prompt, context) {
  const result = await langCache.search({
    prompt,
    similarityThreshold: 0.82,
    searchStrategies: ['exact', 'semantic'],
    // TODO: attributes: pickAttributes(context)
  });
  const matches = result.data || [];
  return { hit: matches.length > 0, match: matches[0] || null };
}

export async function store(prompt, response, context) {
  return langCache.set({
    prompt,
    response,
    ttlMillis: 86_400_000,
    // TODO: attributes: pickAttributes(context)
  });
}

export function pickAttributes(context) {
  // TODO: return only attributes configured in cache-policy.yaml.
  return {};
}
