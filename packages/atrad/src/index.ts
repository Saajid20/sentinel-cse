import { MarketSnapshot } from '@sentinel/core';

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
