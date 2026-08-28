/**
 * Research evidence console client.
 *
 * Renders local R10/R11 artifacts. Presentation only: it never computes a
 * financial figure, and it never renders a scorecard verdict without the values
 * the verdict was derived from.
 */

const METRIC_LABELS = {
  group_profit_for_the_period_yoy_growth: 'profit YoY',
  group_total_assets_growth: 'total assets',
  group_total_liabilities_growth: 'total liabilities',
  group_total_equity_growth: 'total equity'
};

const ACTIONABILITY_COPY = {
  DECIDABLE: 'Yes — judgement call',
  RECOVERABLE: 'Yes — needs diagnosis',
  SOURCE_LIMITED: 'No — source gap',
  BLOCKED: 'No — blocked upstream',
  SETTLED: 'Nothing outstanding'
};

const ACTIONABILITY_CLASS = {
  DECIDABLE: 'sev-decidable',
  RECOVERABLE: 'sev-recoverable',
  SOURCE_LIMITED: '',
  BLOCKED: 'sev-blocked',
  SETTLED: 'sev-settled'
};

const STATE_TAG = {
  CLEAN: 't-clean',
  MANUAL_REVIEW: 't-review',
  PARSE_GAP: 't-absent',
  INSUFFICIENT_EVIDENCE: 't-absent'
};

const FILTERS = [
  { id: 'all', label: 'ALL' },
  { id: 'actionable', label: 'ACTIONABLE' },
  { id: 'flagged', label: 'FLAGGED' },
  { id: 'blocked', label: 'NOT ACTIONABLE' }
];

/** Blind spots are properties of the tooling, not of any single run. */
const BLIND_SPOTS = [
  {
    scope: 'R10 · SOURCES',
    body: 'Corporate actions are unreachable. <b>Cash dividends, name changes, director dealings and ESOS</b> all fail — the detail endpoint serves only "general" announcements.',
    status: 'DEMONSTRATED — the request was made with the right parameter and refused',
    kind: 'demonstrated'
  },
  {
    scope: 'R10 · HISTORY',
    body: 'No historical filings retrieved for PKME. But the client posts an <b>empty payload</b> and filters locally, so a zero result says nothing about what the endpoint holds.',
    status: 'UNTESTED — one probe request would resolve this',
    kind: 'untested'
  },
  {
    scope: 'R11 · CEILING',
    body: '<b>CITH, CITW and REEF publish no labelled liabilities row.</b> These three can never reach a complete metric set from these filings, however good the parser gets.',
    status: 'DEMONSTRATED — source limitation, not a backlog item',
    kind: 'demonstrated'
  },
  {
    scope: 'R11 · SCORING',
    body: 'Balance-sheet risk compares growth rates, never levels. A company whose <b>liabilities exceed its assets</b> can still score MEDIUM.',
    status: 'DEMONSTRATED — awaiting a design decision',
    kind: 'demonstrated'
  },
  {
    scope: 'R11 · INPUT',
    body: 'Some filings yield <b>no extractable text</b>. OCR was deliberately deferred rather than used to paper over a parsing question.',
    status: 'DEFERRED — by choice',
    kind: 'untested'
  }
];

let currentSummary = null;
let activeFilter = 'all';
const expanded = new Set();

function fmt(value) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
}

function signed(value) {
  if (value === null || value === undefined) return '<span>—</span>';
  const cls = value < 0 ? ' class="neg"' : '';
  return `<span${cls}>${fmt(value)}</span>`;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"]/g, (ch) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]
  );
}

function shortMetric(name) {
  return METRIC_LABELS[name] ?? name.replace(/^group_/, '').replace(/_/g, ' ');
}

function renderStats(summary) {
  const { coverage, sources } = summary;
  const cards = [
    {
      n: coverage.tickersAnalysed,
      l: 'Companies analysed',
      d: `${sources.r11Analysis.fileCount} artifacts on disk`
    },
    { n: coverage.goldLabels, l: 'Gold labels', d: 'deterministic validation' },
    { n: coverage.fullyRecovered, l: 'Fully recovered', d: 'no manual review required', cls: 'is-good' },
    { n: coverage.awaitingReview, l: 'Awaiting review', d: 'in the queue below', cls: 'is-attention' },
    {
      n: coverage.integrityFlags,
      l: 'Verdicts flagged',
      d: 'scored on questionable inputs',
      cls: coverage.integrityFlags > 0 ? 'is-attention' : ''
    },
    {
      n: summary.retrieval ? summary.retrieval.matchedCount : 0,
      l: 'R10 documents matched',
      d: summary.retrieval ? 'controls excluded' : 'no retrieval result found'
    }
  ];

  document.getElementById('stat-grid').innerHTML = cards
    .map(
      (card) => `
      <div class="stat ${card.cls ?? ''}">
        <div class="stat-n">${card.n}</div>
        <div class="stat-l">${esc(card.l)}</div>
        <div class="stat-d">${esc(card.d)}</div>
      </div>`
    )
    .join('');

  const safety = summary.safety;
  document.getElementById('posture').innerHTML = [
    `<span class="chip is-ok">TRADE LABELS: ${esc(safety.tradeLabels).toUpperCase()}</span>`,
    `<span class="chip is-ok">ORDER PATH: ${esc(safety.orderPath).toUpperCase()}</span>`,
    `<span class="chip is-ok">SYNTHESIZED VALUES: NONE</span>`,
    `<span class="chip">LABELS: ${safety.researchLabels.map(esc).join(' · ')}</span>`
  ].join('');
}

function primaryReason(entry) {
  const guard = entry.integrity.find((f) => f.severity === 'GUARD_HELD');
  const flag = entry.integrity.find((f) => f.severity === 'FLAG');

  if (flag && flag.code === 'SIGN_FLIP_DENOMINATOR') {
    const fig = flag.figures[0];
    return `Scores clean, but <span class="fig">${esc(flag.field)}=${esc(flag.verdict)}</span> rests on equity crossing zero — <span class="fig">${fmt(fig.previous)}</span> to <span class="fig">${fmt(fig.current)}</span> is a sign flip in the denominator, not a strengthening.`;
  }
  if (guard) {
    return esc(guard.detail);
  }
  if (flag && flag.code === 'LIABILITIES_EXCEED_ASSETS') {
    return `Liabilities <span class="fig">${fmt(flag.figures[1].current)}</span> exceed assets <span class="fig">${fmt(flag.figures[0].current)}</span>, but ${esc(flag.field)} compares growth rates, not levels.`;
  }
  if (entry.missingMetrics.length > 0) {
    const names = entry.missingMetrics.map(shortMetric).map(esc).join(', ');
    // Only say a metric is absent from the filing where that has actually been
    // established. A parse gap means the text extracted but did not map, which
    // is a statement about our parser, not about what the company published.
    const cause =
      entry.state === 'PARSE_GAP'
        ? 'Text extracted but did not map to a metric — a parser gap, not a statement about the filing.'
        : 'Not recovered, and no value is derived to fill the gap.';
    return `Missing <span class="fig">${names}</span>. ${cause}`;
  }
  if (entry.state === 'CLEAN') {
    return 'All core metrics recovered, no conflicts, no integrity concerns raised.';
  }
  return 'Flagged for manual review.';
}

function matchesFilter(entry) {
  if (activeFilter === 'all') return true;
  if (activeFilter === 'flagged') return entry.integrity.some((f) => f.severity === 'FLAG');
  if (activeFilter === 'actionable') {
    return entry.actionability === 'DECIDABLE' || entry.actionability === 'RECOVERABLE';
  }
  return entry.actionability === 'SOURCE_LIMITED' || entry.actionability === 'BLOCKED';
}

function renderQueue(summary) {
  const body = document.getElementById('queue-body');
  const rows = summary.reviewQueue.filter(matchesFilter);

  if (rows.length === 0) {
    const where = summary.sources.r11Analysis;
    const message = where.exists
      ? 'No cases match this filter.'
      : `No analysis artifacts found. Looked in <code>${esc(where.path)}</code>. Start the dashboard from a worktree holding R11 runtime output, or pass <code>--r11-analysis-dir</code>.`;
    body.innerHTML = `<tr><td colspan="6"><div class="state-block">${message}</div></td></tr>`;
    return;
  }

  body.innerHTML = rows
    .map((entry) => {
      const isOpen = expanded.has(entry.ticker);
      const flagged = entry.integrity.some((f) => f.severity === 'FLAG');
      const tagClass = flagged ? 't-flag' : (STATE_TAG[entry.state] ?? 't-absent');
      const tagText = flagged ? 'FLAGGED' : entry.state;

      const main = `
        <tr class="queue-row ${ACTIONABILITY_CLASS[entry.actionability] ?? ''}">
          <td class="cell-ticker">${esc(entry.ticker)}</td>
          <td class="cell-num">${entry.metricsPresent} / ${entry.metricsExpected}</td>
          <td><span class="tag ${tagClass}">${esc(tagText)}</span></td>
          <td class="reason">${primaryReason(entry)}</td>
          <td class="reason">${esc(ACTIONABILITY_COPY[entry.actionability] ?? '—')}</td>
          <td>
            <button type="button" class="disclose" data-ticker="${esc(entry.ticker)}"
              aria-expanded="${isOpen}">${isOpen ? 'Hide' : 'Evidence'}</button>
          </td>
        </tr>`;

      return isOpen ? main + renderDetail(entry) : main;
    })
    .join('');
}

function renderDetail(entry) {
  const verdictCards = entry.integrity
    .map((finding) => {
      const figs = finding.figures
        .map(
          (fig) =>
            `<div class="figures">${esc(shortMetric(fig.metricName))} ${signed(fig.previous)}<span class="arrow">→</span>${signed(fig.current)}<span class="arrow">·</span>${fmt(fig.value)}%</div>`
        )
        .join('');
      const badge =
        finding.severity === 'FLAG'
          ? '<span class="tag t-flag">questioned</span>'
          : '<span class="tag t-review">guard held</span>';
      return `
        <div class="detail-card">
          <h4>${esc(finding.field)}</h4>
          <div class="verdict-line">
            <span class="verdict-value">${esc(finding.verdict ?? 'NOT SCORED')}</span>
            ${badge}
          </div>
          ${figs}
          <p class="detail-why">${esc(finding.detail)}</p>
        </div>`;
    })
    .join('');

  const traceCards = entry.traces
    .slice(0, 2)
    .map(
      (trace) => `
      <div class="detail-card">
        <h4>${esc(shortMetric(trace.metricName))}</h4>
        <div class="trace-line"><span class="k">Page</span><span class="v">${trace.pageNumber ?? '—'}</span></div>
        <div class="trace-line"><span class="k">Row</span><span class="v">${esc(trace.rowLabel ?? '—')}</span></div>
        <div class="raw-row">${esc(trace.rawValue ?? 'no raw row recorded')}</div>
      </div>`
    )
    .join('');

  const metricList = entry.figures
    .map(
      (fig) =>
        `<div class="trace-line"><span class="k">${esc(shortMetric(fig.metricName))}</span><span class="v">${signed(fig.previous)} → ${signed(fig.current)} · ${fmt(fig.value)}%</span></div>`
    )
    .join('');

  return `
    <tr class="detail-row">
      <td colspan="6">
        <div class="detail-grid">
          ${verdictCards}
          <div class="detail-card">
            <h4>Recovered metrics</h4>
            ${metricList || '<p class="detail-why">No metrics recovered.</p>'}
            <p class="detail-why">
              Artifact generated ${entry.generatedAt ? esc(new Date(entry.generatedAt).toLocaleString()) : 'at an unrecorded time'} —
              this console is only as current as the analysis on disk.
            </p>
            <p class="detail-why"><code>${esc(entry.analysisPath)}</code></p>
          </div>
          ${traceCards}
        </div>
      </td>
    </tr>`;
}

function renderBlindSpots() {
  document.getElementById('blind-list').innerHTML = BLIND_SPOTS.map(
    (item) => `
      <div class="blind-item">
        <div class="scope">${esc(item.scope)}</div>
        <div class="body">
          ${item.body}
          <div class="status-line ${item.kind}">${esc(item.status)}</div>
        </div>
      </div>`
  ).join('');
}

function renderRetrieval(summary) {
  const host = document.getElementById('retrieval-body');
  const retrieval = summary.retrieval;

  if (!retrieval) {
    const where = summary.sources.r10Retrieval;
    host.innerHTML = `<div class="state-block">No retrieval result found. Looked in <code>${esc(where.path)}</code>.</div>`;
    return;
  }

  const rows = retrieval.documents
    .map(
      (doc) => `
      <tr class="queue-row">
        <td>${esc(doc.title)}</td>
        <td class="cell-num">${doc.score ?? '—'}</td>
        <td>
          <div class="sig-list">
            ${doc.documentDerived.map((r) => `<span class="sig from-doc">${esc(r.replace(/^keyword:/, ''))}</span>`).join('')}
            ${doc.annotationDerived.map((r) => `<span class="sig from-annotation">${esc(r)}</span>`).join('')}
          </div>
        </td>
      </tr>`
    )
    .join('');

  host.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th scope="col">Document</th><th scope="col">Score</th><th scope="col">Matched on</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="legend">
      <span><span class="swatch" style="color:var(--verified);background:var(--verified-soft)"></span> derived from the document</span>
      <span><span class="swatch" style="color:var(--absent);background:var(--absent-soft);border-style:dashed"></span> derived from our own annotation</span>
      <span>${esc(retrieval.matchedCount)} matched · store <code>${esc(retrieval.storePath ?? 'unknown')}</code></span>
    </div>`;
}

function renderFilters(summary) {
  const host = document.getElementById('filters');
  host.innerHTML = FILTERS.map((filter) => {
    const count = summary.reviewQueue.filter((entry) => {
      const previous = activeFilter;
      activeFilter = filter.id;
      const result = matchesFilter(entry);
      activeFilter = previous;
      return result;
    }).length;
    return `<button type="button" class="filter" data-filter="${filter.id}"
      aria-pressed="${activeFilter === filter.id}">${filter.label} ${count}</button>`;
  }).join('');
}

function render(summary) {
  currentSummary = summary;
  renderStats(summary);
  renderFilters(summary);
  renderQueue(summary);
  renderBlindSpots();
  renderRetrieval(summary);
  document.getElementById('refresh-state').textContent = new Date(
    summary.generatedAt
  ).toLocaleTimeString();
}

async function load() {
  const button = document.getElementById('refresh-button');
  const errorHost = document.getElementById('load-error');
  button.setAttribute('aria-busy', 'true');
  button.textContent = 'Reading…';

  try {
    const response = await fetch('/api/research', { headers: { accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }
    render(await response.json());
    errorHost.hidden = true;
    errorHost.innerHTML = '';
  } catch (error) {
    errorHost.hidden = false;
    errorHost.innerHTML = `<div class="state-block is-error">Could not read artifacts: ${esc(
      error.message
    )}. The console shows nothing rather than showing stale figures.</div>`;
  } finally {
    button.removeAttribute('aria-busy');
    button.textContent = 'Refresh';
  }
}

document.addEventListener('click', (event) => {
  const disclose = event.target.closest('.disclose');
  if (disclose) {
    const ticker = disclose.dataset.ticker;
    if (expanded.has(ticker)) {
      expanded.delete(ticker);
    } else {
      expanded.add(ticker);
    }
    renderQueue(currentSummary);
    return;
  }

  const filter = event.target.closest('.filter');
  if (filter) {
    activeFilter = filter.dataset.filter;
    renderFilters(currentSummary);
    renderQueue(currentSummary);
  }
});

document.getElementById('refresh-button').addEventListener('click', load);
load();
