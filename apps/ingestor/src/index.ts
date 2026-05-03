import {
  ATradObservedTicker,
  MockATradObserver,
  MockATradSessionManager
} from '@sentinel/atrad';
import { MarketSnapshot } from '@sentinel/core';

export interface MockIngestorResult {
  watchlist: ATradObservedTicker[];
  snapshots: MarketSnapshot[];
}

const defaultWatchlist: ATradObservedTicker[] = [
  {
    ticker: 'SAMP.N0000',
    enabled: true,
    displayName: 'Sample One',
    source: 'mock'
  },
  {
    ticker: 'TEST.N0000',
    enabled: true,
    displayName: 'Sample Two',
    source: 'mock'
  }
];

export async function runMockIngestor(
  watchlist: ATradObservedTicker[] = defaultWatchlist
): Promise<MockIngestorResult> {
  const session = new MockATradSessionManager();
  await session.startObservationSession();

  const observer = new MockATradObserver();
  await observer.setWatchlist(watchlist);

  const snapshots = await observer.observeOnce();
  await session.stopObservationSession();

  return {
    watchlist: await observer.getWatchlist(),
    snapshots
  };
}

export async function printMockSnapshots(): Promise<MarketSnapshot[]> {
  const result = await runMockIngestor();
  console.log(JSON.stringify(result.snapshots, null, 2));
  return result.snapshots;
}
