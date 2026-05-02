import { MarketSnapshot, Signal } from '@sentinel/core';
import { SentinelPipeline } from './pipeline.js';

const FINAL_STATUSES = new Set(['EXPIRED', 'INVALIDATED', 'TARGET_HIT', 'STOP_HIT', 'ENDED']);

export interface ReplayOptions {
  speed?: 'instant' | number;
  tickerFilter?: string | string[];
  stopOnFinalSignal?: boolean;
}

export interface ReplayResultSummary {
  snapshotsProcessed: number;
  signalsGenerated: number;
  alertsSent: number;
  outcomesClosed: number;
  finalActiveSignals: Signal[];
  startTime?: number;
  endTime?: number;
}

export class MarketReplayEngine {
  async replay(
    snapshots: MarketSnapshot[],
    pipeline: SentinelPipeline,
    options: ReplayOptions = {}
  ): Promise<ReplayResultSummary> {
    const orderedSnapshots = this.filterSnapshots(snapshots, options.tickerFilter).sort(
      (left, right) => left.timestamp - right.timestamp
    );

    let snapshotsProcessed = 0;
    let signalsGenerated = 0;
    let alertsSent = 0;
    let outcomesClosed = 0;
    let startTime: number | undefined;
    let endTime: number | undefined;

    for (const snapshot of orderedSnapshots) {
      startTime ??= snapshot.timestamp;
      endTime = snapshot.timestamp;

      const result = await pipeline.processSnapshot(snapshot);
      snapshotsProcessed += 1;
      signalsGenerated += result.generatedSignal ? 1 : 0;
      alertsSent += result.sentMessages.length;

      const finalEvents = result.events.filter((event) => FINAL_STATUSES.has(event.newStatus));
      outcomesClosed += finalEvents.length;

      if (options.stopOnFinalSignal && finalEvents.length > 0) {
        break;
      }
    }

    return {
      snapshotsProcessed,
      signalsGenerated,
      alertsSent,
      outcomesClosed,
      finalActiveSignals: await pipeline.listActiveSignals(),
      startTime,
      endTime
    };
  }

  private filterSnapshots(
    snapshots: MarketSnapshot[],
    tickerFilter: ReplayOptions['tickerFilter']
  ): MarketSnapshot[] {
    if (!tickerFilter) return [...snapshots];

    const allowedTickers = new Set(Array.isArray(tickerFilter) ? tickerFilter : [tickerFilter]);
    return snapshots.filter((snapshot) => allowedTickers.has(snapshot.ticker));
  }
}
