import { naiveResult, runMine, runRetrievalCases } from './arena/run.js';

const scoreboard = document.querySelector('#scoreboard');
const caseList = document.querySelector('#case-list');
const status = document.querySelector('#status');

const metrics = [
  ['accuracy', 'Accuracy', '%', true],
  ['promptTokens', 'Prompt tokens', '', false],
  ['p50LatencyMs', 'p50 latency', ' ms', false],
  ['peakContextTokens', 'Peak context', ' tokens', false],
];

function render(result) {
  scoreboard.innerHTML = metrics.map(([key, label, suffix, higherIsBetter]) => {
    const value = result[key] ?? 0;
    const max = key === 'accuracy' ? 100 : Math.max(value, naiveResult[key], 1);
    const width = key === 'accuracy'
      ? value
      : higherIsBetter ? (value / max) * 100 : 100 - (value / max) * 75;
    return `
      <article class="metric">
        <span>${label}</span>
        <strong>${Number(value).toLocaleString()}${suffix}</strong>
        <div class="track"><i style="width:${Math.max(4, width)}%"></i></div>
      </article>`;
  }).join('') + `
    <article class="cost">
      <span>Illustrative cost at 12M requests/day</span>
      <strong>$${Math.round(result.dailyCost || 0).toLocaleString()}/day</strong>
      <small>Uses a documented $5 / 1M-token workshop assumption—not a quote.</small>
    </article>`;

  caseList.innerHTML = result.cases?.length
    ? result.cases.map((item) => `
        <div class="case ${item.passed ? 'pass' : 'fail'}">
          <b>${item.passed ? 'PASS' : 'MISS'}</b>
          <span>${item.id}</span>
          <small>${item.detail || ''}</small>
        </div>`).join('')
    : '<p>The naive reference is fixed so every team starts from the same line.</p>';
}

async function execute(label, runner) {
  document.querySelectorAll('button').forEach((button) => { button.disabled = true; });
  status.textContent = label;
  try {
    const result = await runner((message) => { status.textContent = message; });
    const averageTokens = result.promptTokens / Math.max(result.total || 1, 1);
    result.dailyCost ??= (averageTokens / 1_000_000) * 12_000_000 * 5;
    render(result);
    status.textContent = `${result.name}: ${result.passed ?? 0}/${result.total ?? 0} cases passed.`;
  } catch (error) {
    status.textContent = `Run failed: ${error.message}`;
  } finally {
    document.querySelectorAll('button').forEach((button) => { button.disabled = false; });
  }
}

document.querySelector('#naive').addEventListener('click', () => {
  render(naiveResult);
  status.textContent = 'Naive reference loaded.';
});
document.querySelector('#retrieve').addEventListener('click', () =>
  execute('Running retrieval cases…', runRetrievalCases));
document.querySelector('#mine').addEventListener('click', () =>
  execute('Running full arena…', runMine));

fetch('/app/iris/health')
  .then((response) => response.json())
  .then((health) => {
    const ready = Object.entries(health).filter(([, value]) => value).map(([key]) => key);
    document.querySelector('#health').textContent = `${ready.length}/4 services ready`;
    document.querySelector('#health').classList.toggle('ready', ready.length === 4);
  })
  .catch(() => { document.querySelector('#health').textContent = 'Iris proxy unavailable'; });

render(naiveResult);
