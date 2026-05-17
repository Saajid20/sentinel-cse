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

const refreshState = document.querySelector('#refresh-state');
const commands = document.querySelector('#commands');

loadDashboard();

async function loadDashboard() {
  try {
    const response = await fetch('/api/dashboard', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const summary = await response.json();
    renderDashboard(summary);
    refreshState.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    refreshState.dataset.ready = 'true';
  } catch (error) {
    refreshState.textContent = 'Local dashboard unavailable';
    fields.get('recommendation').textContent = error instanceof Error ? error.message : String(error);
  }
}

function renderDashboard(summary) {
  const localFiles = summary.localFiles || {};
  const latest = summary.latestSession;
  const universe = summary.tradeableUniverse || {};
  const readiness = latest?.replayReadiness;

  setText('sessionsDir', localFiles.sessionsDir || 'data/live-sessions');
  setText('folderExists', localFiles.exists ? 'yes' : 'no');
  setText('sessionFileCount', localFiles.sessionFileCount ?? 0);
  setText('latestSessionFilePath', localFiles.latestSessionFilePath || 'none');

  setText('sessionId', latest?.sessionId || 'none');
  setText('startedAt', latest?.startedAt || 'n/a');
  setText('endedAt', latest?.endedAt || 'n/a');
  setText('source', latest?.source || 'n/a');
  setText('mode', latest?.mode || 'n/a');
  setText('usableSnapshots', latest?.totals?.usableSnapshots ?? 0);
  setText('quarantinedSnapshots', latest?.totals?.quarantinedSnapshots ?? 0);
  setText('rejectedSnapshots', latest?.totals?.rejectedSnapshots ?? 0);

  for (const state of ['OPEN', 'CLOSED', 'INACTIVE', 'UNKNOWN']) {
    const element = stateFields.get(state);
    if (element) element.textContent = latest?.marketStates?.[state] ?? 0;
  }

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
  setText('likelyUsefulForReplay', readiness?.likelyUsefulForReplay ? 'yes' : 'no');
  setText('recommendation', summary.recommendation || 'Review local session and universe config.');

  renderCommands(summary.commandSnippets || []);
}

function renderCommands(snippets) {
  commands.replaceChildren();
  for (const snippet of snippets) {
    const row = document.createElement('div');
    row.className = 'command-row';

    const label = document.createElement('span');
    label.className = 'command-label';
    label.textContent = snippet.label;

    const code = document.createElement('code');
    code.textContent = snippet.command;

    const button = document.createElement('button');
    button.type = 'button';
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
  if (element) element.textContent = String(value);
}

function joinOrNone(value) {
  return Array.isArray(value) && value.length > 0 ? value.join(', ') : 'none';
}
