import { MarketSnapshot } from '@sentinel/core';

const DEFAULT_FORBIDDEN_READONLY_TERMS = [
  'buy',
  'sell',
  'order',
  'submit',
  'confirm',
  'quantity',
  'price input',
  'market order',
  'limit order'
];

export interface ATradSessionState {
  isAuthenticated: boolean;
  sessionStartedAt?: number;
  storageStatePath?: string;
  lastHeartbeatAt?: number;
  notes: string[];
}

export interface ATradObservedTicker {
  ticker: string;
  enabled: boolean;
  displayName?: string;
  source?: string;
}

export interface ATradSessionManager {
  getSessionState(): Promise<ATradSessionState>;
  startObservationSession(): Promise<ATradSessionState>;
  stopObservationSession(): Promise<ATradSessionState>;
  refreshHeartbeat(): Promise<ATradSessionState>;
}

export interface ATradObserver {
  setWatchlist(tickers: ATradObservedTicker[]): Promise<void>;
  getWatchlist(): Promise<ATradObservedTicker[]>;
  observeOnce(): Promise<MarketSnapshot[]>;
  observeMany(count: number): Promise<MarketSnapshot[][]>;
}

export interface ATradReadOnlySafetyConfig {
  readonlyMode: true;
  forbiddenTerms?: string[];
}

export interface ATradReadOnlySafetyCheck {
  safe: boolean;
  violations: string[];
}

export interface PlaywrightATradSessionConfig {
  baseUrl: string;
  storageStatePath: string;
  headless: boolean;
  observationTimeoutMs: number;
  readonlyMode: true;
  safety?: ATradReadOnlySafetyConfig;
}

export interface PlaywrightATradObserverConfig extends PlaywrightATradSessionConfig {
  watchlist: ATradObservedTicker[];
}

export interface ATradReadOnlyPageAdapter {
  observeReadOnlySnapshots(
    watchlist: ATradObservedTicker[],
    config: PlaywrightATradObserverConfig
  ): Promise<MarketSnapshot[]>;
}

export function checkATradReadOnlySafety(
  description: string,
  config: ATradReadOnlySafetyConfig = { readonlyMode: true }
): ATradReadOnlySafetyCheck {
  const normalized = description.toLowerCase();
  const forbiddenTerms = config.forbiddenTerms ?? DEFAULT_FORBIDDEN_READONLY_TERMS;
  const violations = forbiddenTerms.filter((term) => normalized.includes(term.toLowerCase()));

  return {
    safe: violations.length === 0,
    violations
  };
}

export function assertATradReadOnlySafety(
  description: string,
  config: ATradReadOnlySafetyConfig = { readonlyMode: true }
): void {
  if (config.readonlyMode !== true) {
    throw new Error('ATrad observer scaffold requires readonlyMode: true.');
  }

  const result = checkATradReadOnlySafety(description, config);
  if (!result.safe) {
    throw new Error(`Unsafe ATrad read-only action description: ${result.violations.join(', ')}`);
  }
}

export class MockATradSessionManager implements ATradSessionManager {
  private state: ATradSessionState = {
    isAuthenticated: false,
    notes: ['Mock observation session only. No ATrad login is performed.']
  };

  constructor(private readonly clock: () => number = Date.now) {}

  async getSessionState(): Promise<ATradSessionState> {
    return this.cloneState();
  }

  async startObservationSession(): Promise<ATradSessionState> {
    const now = this.clock();
    this.state = {
      isAuthenticated: false,
      sessionStartedAt: now,
      storageStatePath: undefined,
      lastHeartbeatAt: now,
      notes: ['Mock observation session started without authentication.']
    };

    return this.cloneState();
  }

  async stopObservationSession(): Promise<ATradSessionState> {
    this.state = {
      ...this.state,
      isAuthenticated: false,
      lastHeartbeatAt: this.clock(),
      notes: [...this.state.notes, 'Mock observation session stopped.']
    };

    return this.cloneState();
  }

  async refreshHeartbeat(): Promise<ATradSessionState> {
    this.state = {
      ...this.state,
      lastHeartbeatAt: this.clock(),
      notes: [...this.state.notes, 'Mock heartbeat refreshed.']
    };

    return this.cloneState();
  }

  private cloneState(): ATradSessionState {
    return {
      ...this.state,
      notes: [...this.state.notes]
    };
  }
}

export class MockATradObserver implements ATradObserver {
  private watchlist: ATradObservedTicker[] = [];
  private observationCount = 0;

  constructor(
    tickers: ATradObservedTicker[] = [],
    private readonly clock: () => number = Date.now
  ) {
    this.watchlist = this.cloneWatchlist(tickers);
  }

  async setWatchlist(tickers: ATradObservedTicker[]): Promise<void> {
    this.watchlist = this.cloneWatchlist(tickers);
  }

  async getWatchlist(): Promise<ATradObservedTicker[]> {
    return this.cloneWatchlist(this.watchlist);
  }

  async observeOnce(): Promise<MarketSnapshot[]> {
    const batchIndex = this.observationCount;
    this.observationCount += 1;

    return this.watchlist
      .filter((ticker) => ticker.enabled)
      .map((ticker, index) => this.toMockSnapshot(ticker, index, batchIndex));
  }

  async observeMany(count: number): Promise<MarketSnapshot[][]> {
    const batches: MarketSnapshot[][] = [];
    const safeCount = Math.max(0, Math.floor(count));

    for (let index = 0; index < safeCount; index += 1) {
      batches.push(await this.observeOnce());
    }

    return batches;
  }

  private toMockSnapshot(
    observedTicker: ATradObservedTicker,
    tickerIndex: number,
    batchIndex: number
  ): MarketSnapshot {
    const basePrice = 50 + tickerIndex * 10;
    const lastPrice = basePrice + batchIndex;
    const timestamp = this.clock() + batchIndex * 1_000;

    return {
      ticker: observedTicker.ticker,
      timestamp,
      lastPrice,
      bestBid: lastPrice - 0.5,
      bestAsk: lastPrice + 0.5,
      bidDepth: 1_000 + tickerIndex * 100,
      askDepth: 900 + tickerIndex * 100,
      volume: 100 + batchIndex * 10,
      totalTurnover: lastPrice * (100 + batchIndex * 10)
    };
  }

  private cloneWatchlist(tickers: ATradObservedTicker[]): ATradObservedTicker[] {
    return tickers.map((ticker) => ({ ...ticker }));
  }
}

export class PlaywrightATradSessionManager implements ATradSessionManager {
  private state: ATradSessionState;

  constructor(
    private readonly config: PlaywrightATradSessionConfig,
    private readonly clock: () => number = Date.now
  ) {
    this.assertReadonlyConfig(config);
    this.state = {
      isAuthenticated: false,
      storageStatePath: config.storageStatePath,
      notes: [
        'Playwright ATrad read-only scaffold initialized.',
        'No browser is launched and no login is performed by this scaffold.'
      ]
    };
  }

  async getSessionState(): Promise<ATradSessionState> {
    return this.cloneState();
  }

  async startObservationSession(): Promise<ATradSessionState> {
    assertATradReadOnlySafety('start read-only market observation session', this.safetyConfig());
    const now = this.clock();
    this.state = {
      isAuthenticated: false,
      sessionStartedAt: now,
      storageStatePath: this.config.storageStatePath,
      lastHeartbeatAt: now,
      notes: [
        'Playwright ATrad read-only observation session started.',
        'Automated login and browser launch are intentionally not implemented.'
      ]
    };

    return this.cloneState();
  }

  async stopObservationSession(): Promise<ATradSessionState> {
    this.state = {
      ...this.state,
      isAuthenticated: false,
      lastHeartbeatAt: this.clock(),
      notes: [...this.state.notes, 'Playwright ATrad read-only observation session stopped.']
    };

    return this.cloneState();
  }

  async refreshHeartbeat(): Promise<ATradSessionState> {
    this.state = {
      ...this.state,
      lastHeartbeatAt: this.clock(),
      notes: [...this.state.notes, 'Playwright ATrad read-only heartbeat refreshed.']
    };

    return this.cloneState();
  }

  private assertReadonlyConfig(config: PlaywrightATradSessionConfig): void {
    if (config.readonlyMode !== true) {
      throw new Error('Playwright ATrad session config must set readonlyMode: true.');
    }
  }

  private safetyConfig(): ATradReadOnlySafetyConfig {
    return this.config.safety ?? { readonlyMode: true };
  }

  private cloneState(): ATradSessionState {
    return {
      ...this.state,
      notes: [...this.state.notes]
    };
  }
}

export class PlaywrightATradObserver implements ATradObserver {
  private watchlist: ATradObservedTicker[];

  constructor(
    private readonly sessionManager: ATradSessionManager,
    private readonly config: PlaywrightATradObserverConfig,
    private readonly pageAdapter?: ATradReadOnlyPageAdapter
  ) {
    this.assertReadonlyConfig(config);
    this.watchlist = this.cloneWatchlist(config.watchlist);
  }

  async setWatchlist(tickers: ATradObservedTicker[]): Promise<void> {
    this.watchlist = this.cloneWatchlist(tickers);
  }

  async getWatchlist(): Promise<ATradObservedTicker[]> {
    return this.cloneWatchlist(this.watchlist);
  }

  async observeOnce(): Promise<MarketSnapshot[]> {
    assertATradReadOnlySafety('observe read-only market snapshot fields', this.safetyConfig());
    await this.sessionManager.refreshHeartbeat();

    if (!this.pageAdapter) {
      return [];
    }

    const enabledWatchlist = this.watchlist.filter((ticker) => ticker.enabled);
    return this.pageAdapter.observeReadOnlySnapshots(enabledWatchlist, {
      ...this.config,
      watchlist: this.cloneWatchlist(enabledWatchlist)
    });
  }

  async observeMany(count: number): Promise<MarketSnapshot[][]> {
    const batches: MarketSnapshot[][] = [];
    const safeCount = Math.max(0, Math.floor(count));

    for (let index = 0; index < safeCount; index += 1) {
      batches.push(await this.observeOnce());
    }

    return batches;
  }

  private assertReadonlyConfig(config: PlaywrightATradObserverConfig): void {
    if (config.readonlyMode !== true) {
      throw new Error('Playwright ATrad observer config must set readonlyMode: true.');
    }
  }

  private safetyConfig(): ATradReadOnlySafetyConfig {
    return this.config.safety ?? { readonlyMode: true };
  }

  private cloneWatchlist(tickers: ATradObservedTicker[]): ATradObservedTicker[] {
    return tickers.map((ticker) => ({ ...ticker }));
  }
}
