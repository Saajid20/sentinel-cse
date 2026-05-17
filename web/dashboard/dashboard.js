const fields = new Map(
  Array.from(document.querySelectorAll('[data-field]')).map((element) => [
    element.dataset.field,
    element
  ])
);

const stateFields = new Map(
  Array.from(document.querySelectorAll('[data-state]')).map((element) => [
    element.dataset.state,
    element
  ])
);

const stateBars = new Map(
  Array.from(document.querySelectorAll('[data-state-bar]')).map((element) => [
    element.dataset.stateBar,
    element
  ])
);

const refreshState = document.querySelector('#refresh-state');
const refreshButton = document.querySelector('#refresh-button');
const commands = document.querySelector('#commands');

refreshButton?.addEventListener('click', () => {
  void loadDashboard();
});

void loadDashboard();

async function loadDashboard() {
  if (refreshButton) {
    refreshButton.disabled = true;
    refreshButton.textContent = 'Refreshing';
  }

  try {
    const response = await fetch('/api/dashboard', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const summary = await response.json();
    renderDashboard(summary);
    refreshState.textContent = new Date().toLocaleString();
    refreshState.dataset.ready = 'true';
  } catch (error) {
    refreshState.textContent = 'Local dashboard unavailable';
    fields.get('recommendation').textContent = error instanceof Error ? error.message : String(error);
  } finally {
    if (refreshButton) {
      refreshButton.disabled = false;
      refreshButton.textContent = 'Refresh';
    }
  }
}

function renderDashboard(summary) {
  const localFiles = summary.localFiles || {};
  const latest = summary.latestSession;
  const universe = summary.tradeableUniverse || {};
  const readiness = latest?.replayReadiness;
  const totals = latest?.totals || {};

  document.querySelector('#metric-atrad').textContent = summary.safety?.atradMode || 'read-only/manual';
  document.querySelector('#metric-auto').textContent = summary.safety?.autoTrading || 'disabled';
  document.querySelector('#metric-orders').textContent = summary.safety?.orderPlacement || 'disabled';
  document.querySelector('#metric-services').textContent =
    summary.safety?.telegramLiveAlerts === 'disabled' &&
    summary.safety?.supabaseLiveWrites === 'disabled' &&
    summary.safety?.liveSentinelPipelineFromATrad === 'disabled'
      ? 'disabled'
      : 'review';

  setText('sessionsDir', localFiles.sessionsDir || 'data/live-sessions');
  setText('folderExists', localFiles.exists ? 'exists' : 'missing');
  setText('sessionFileCount', localFiles.sessionFileCount ?? 0);
  setText('latestSessionFilePath', localFiles.latestSessionFilePath || 'none');

  setText('sessionId', latest?.sessionId || 'none');
  setText('startedAt', latest?.startedAt || 'n/a');
  setText('endedAt', latest?.endedAt || 'n/a');
  setText('source', latest?.source || 'n/a');
  setText('mode', latest?.mode || 'n/a');
  setText('ticksAttempted', totals.ticksAttempted ?? 0);
  setText('usableSnapshots', totals.usableSnapshots ?? 0);
  setText('quarantinedSnapshots', totals.quarantinedSnapshots ?? 0);
  setText('rejectedSnapshots', totals.rejectedSnapshots ?? 0);

  const marketStates = latest?.marketStates || { OPEN: 0, CLOSED: 0, INACTIVE: 0, UNKNOWN: 0 };
  for (const state of ['OPEN', 'CLOSED', 'INACTIVE', 'UNKNOWN']) {
    const element = stateFields.get(state);
    if (element) {
      element.textContent = marketStates[state] ?? 0;
    }
  }
  updateStateBar(marketStates);

  setText('universeSource', universe.source || 'missing');
  setText('universeName', universe.name || 'n/a');
  setText('includeTickersCount', universe.includeTickersCount ?? 0);
  setText('includedTickersPreview', joinOrNone(universe.includedTickersPreview));
  setText('excludePatterns', joinOrNone(universe.excludePatterns));
  setText('excludeNonVoting', universe.excludeNonVoting ? 'yes' : 'no');
  setText('maximumSpreadPercent', universe.maximumSpreadPercent ?? 'n/a');
  setText('minimumConfidence', universe.minimumConfidence || 'n/a');

  setText('snapshotsCount', readiness?.snapshotsCount ?? 0);
  setText('uniqueTickers', readiness?.uniqueTickers ?? 0);
  setText('repeatedTickersEstimate', readiness?.repeatedTickersEstimate ?? 0);
  setText('likelyUsefulForReplay', readiness?.likelyUsefulForReplay ? 'useful' : 'not ready');
  setText('recommendation', summary.recommendation || 'Review local session and universe config.');

  renderCommands(summary.commandSnippets || []);
}

function updateStateBar(marketStates) {
  const total = Object.values(marketStates).reduce((sum, value) => sum + Number(value || 0), 0);
  for (const state of ['OPEN', 'CLOSED', 'INACTIVE', 'UNKNOWN']) {
    const element = stateBars.get(state);
    if (!element) {
      continue;
    }

    const value = Number(marketStates[state] || 0);
    const width = total > 0 ? `${(value / total) * 100}%` : '0%';
    element.style.width = width;
    element.style.opacity = value > 0 ? '1' : '0.2';
  }
}

function renderCommands(snippets) {
  commands.replaceChildren();
  for (const snippet of snippets) {
    const row = document.createElement('div');
    row.className = 'command-row';

    const label = document.createElement('div');
    label.className = 'command-meta';

    const labelTitle = document.createElement('span');
    labelTitle.className = 'command-label';
    labelTitle.textContent = snippet.label;

    const labelHint = document.createElement('span');
    labelHint.className = 'command-hint';
    labelHint.textContent = 'Text only';

    label.append(labelTitle, labelHint);

    const code = document.createElement('code');
    code.textContent = snippet.command;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'copy-button';
    button.textContent = 'Copy';
    button.addEventListener('click', async () => {
      await navigator.clipboard.writeText(snippet.command);
      button.textContent = 'Copied';
      setTimeout(() => {
        button.textContent = 'Copy';
      }, 1200);
    });

    row.append(label, code, button);
    commands.append(row);
  }
}

function setText(field, value) {
  const element = fields.get(field);
  if (element) {
    element.textContent = String(value);
  }
}

function joinOrNone(value) {
  return Array.isArray(value) && value.length > 0 ? value.join(', ') : 'none';
}
