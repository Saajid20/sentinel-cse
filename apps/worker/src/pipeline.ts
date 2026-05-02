import {
  BasicCandleAgent,
  BasicMonitorAgent,
  Candle,
  InMemorySignalMemory,
  MarketSnapshot,
  Signal,
  SignalEvent,
  SignalOutcome,
  SignalStatus
} from '@sentinel/core';
import {
  DbSignal,
  DbSignalEvent,
  DbSignalOutcome,
  InMemoryDbAdapter,
  JsonObject
} from '@sentinel/db';
import { OpeningMomentumDetector } from '@sentinel/strategies';
import {
  MockTelegramAlertSender,
  TelegramAlertFormatter,
  TelegramAlertMessage
} from '@sentinel/telegram';

const FINAL_STATUSES = new Set<SignalStatus>(['EXPIRED', 'INVALIDATED', 'TARGET_HIT', 'STOP_HIT', 'ENDED']);

export interface SentinelPipelineOptions {
  candleAgent?: BasicCandleAgent;
  monitorAgent?: BasicMonitorAgent;
  detector?: OpeningMomentumDetector;
  memory?: InMemorySignalMemory;
  db?: InMemoryDbAdapter;
  formatter?: TelegramAlertFormatter;
  sender?: MockTelegramAlertSender;
}

export interface ProcessSnapshotResult {
  generatedSignal?: Signal;
  updatedSignals: Signal[];
  events: SignalEvent[];
  sentMessages: TelegramAlertMessage[];
}

export class SentinelPipeline {
  public readonly candleAgent: BasicCandleAgent;
  public readonly monitorAgent: BasicMonitorAgent;
  public readonly detector: OpeningMomentumDetector;
  public readonly memory: InMemorySignalMemory;
  public readonly db: InMemoryDbAdapter;
  public readonly formatter: TelegramAlertFormatter;
  public readonly sender: MockTelegramAlertSender;

  constructor(options: SentinelPipelineOptions = {}) {
    this.candleAgent = options.candleAgent ?? new BasicCandleAgent();
    this.monitorAgent = options.monitorAgent ?? new BasicMonitorAgent();
    this.detector = options.detector ?? new OpeningMomentumDetector();
    this.memory = options.memory ?? new InMemorySignalMemory();
    this.db = options.db ?? new InMemoryDbAdapter();
    this.formatter = options.formatter ?? new TelegramAlertFormatter();
    this.sender = options.sender ?? new MockTelegramAlertSender();
  }

  async processSnapshot(snapshot: MarketSnapshot): Promise<ProcessSnapshotResult> {
    const messagesBefore = this.sender.listSentMessages().length;

    await this.db.marketSnapshots.save(this.toDbMarketSnapshot(snapshot));

    const closedCandle = this.candleAgent.process(snapshot);
    if (closedCandle) {
      await this.db.candles.save(this.toDbCandle(closedCandle));
    }

    const activeBefore = (await this.memory.listActiveSignals()).filter(
      (signal) => signal.ticker === snapshot.ticker
    );
    const { updatedSignals, events } = await this.monitorSignals(snapshot, activeBefore);

    let generatedSignal: Signal | undefined;
    if (activeBefore.length === 0) {
      generatedSignal = await this.detectAndAlert(snapshot);
    }

    const sentMessages = this.sender.listSentMessages().slice(messagesBefore);
    return {
      generatedSignal,
      updatedSignals,
      events,
      sentMessages
    };
  }

  async listActiveSignals(): Promise<Signal[]> {
    return this.memory.listActiveSignals();
  }

  private async monitorSignals(
    snapshot: MarketSnapshot,
    activeSignals: Signal[]
  ): Promise<{ updatedSignals: Signal[]; events: SignalEvent[] }> {
    const updatedSignals: Signal[] = [];
    const events: SignalEvent[] = [];

    for (const activeSignal of activeSignals) {
      const updatedSignal = await this.monitorAgent.monitor(activeSignal, snapshot);
      updatedSignals.push(updatedSignal);

      await this.memory.updateSignal(updatedSignal);
      await this.db.signals.update(this.toDbSignal(updatedSignal));

      if (updatedSignal.status !== activeSignal.status) {
        const event = this.toSignalEvent(activeSignal, updatedSignal);
        events.push(event);

        await this.memory.recordEvent(event);
        await this.db.signalEvents.record(this.toDbSignalEvent(event));

        const updateMessage = this.formatter.formatSignalUpdate(updatedSignal);
        await this.sender.send(updateMessage);
      }

      if (FINAL_STATUSES.has(updatedSignal.status)) {
        const outcome = this.toSignalOutcome(updatedSignal);
        await this.memory.closeSignalOutcome(outcome);
        await this.db.signalOutcomes.save(this.toDbSignalOutcome(outcome, updatedSignal));
      }
    }

    return { updatedSignals, events };
  }

  private async detectAndAlert(snapshot: MarketSnapshot): Promise<Signal | undefined> {
    const candles = this.candleAgent.getCandles(snapshot.ticker);
    const setup = await this.detector.detect(snapshot, candles);
    if (!setup) return undefined;

    const signal = this.toSignal(setup, snapshot);

    await this.memory.saveSignal(signal);
    await this.db.signals.save(this.toDbSignal(signal));

    const alert = this.formatter.formatBuyWatch(signal);
    await this.sender.send(alert);

    return signal;
  }

  private toSignal(setup: Partial<Signal>, snapshot: MarketSnapshot): Signal {
    const timestamp = setup.timestamp ?? snapshot.timestamp;
    const strategy = setup.strategy ?? 'CSE_OPENING_MOMENTUM_V1';

    return {
      id: this.signalId(snapshot.ticker, strategy, timestamp),
      ticker: snapshot.ticker,
      strategy,
      timestamp,
      type: setup.type ?? 'BUY_WATCH',
      entryZone: setup.entryZone ?? [snapshot.lastPrice, snapshot.lastPrice],
      stopLoss: setup.stopLoss ?? snapshot.lastPrice,
      targets: setup.targets ?? [],
      validUntil: setup.validUntil ?? timestamp + 10 * 60 * 1000,
      features: setup.features ?? {},
      status: 'ACTIVE',
      latestPrice: snapshot.lastPrice,
      lastCheckedAt: snapshot.timestamp,
      maxFavorableMovePercent: 0,
      maxAdverseMovePercent: 0,
      statusReason: 'Signal generated'
    };
  }

  private toSignalEvent(previous: Signal, current: Signal): SignalEvent {
    const timestamp = current.lastCheckedAt ?? current.timestamp;

    return {
      id: `event-${current.id}-${timestamp}-${current.status}`,
      signalId: current.id,
      timestamp,
      previousStatus: previous.status,
      newStatus: current.status,
      reason: current.statusReason ?? 'Status changed',
      latestPrice: current.latestPrice ?? 0
    };
  }

  private toSignalOutcome(signal: Signal): SignalOutcome {
    const entryPrice = this.entryPrice(signal);
    const exitPrice = signal.latestPrice ?? entryPrice;
    const returnPercent = this.returnPercent(signal, entryPrice, exitPrice);

    return {
      signalId: signal.id,
      finalStatus: signal.status,
      entryPrice,
      exitPrice,
      returnPercent,
      maxFavorableMovePercent: signal.maxFavorableMovePercent ?? 0,
      maxAdverseMovePercent: signal.maxAdverseMovePercent ?? 0,
      openedAt: signal.timestamp,
      closedAt: signal.lastCheckedAt ?? signal.timestamp,
      closeReason: signal.statusReason ?? signal.status
    };
  }

  private toDbMarketSnapshot(snapshot: MarketSnapshot) {
    return {
      id: `snapshot-${snapshot.ticker}-${snapshot.timestamp}`,
      ticker: snapshot.ticker,
      snapshotTime: snapshot.timestamp,
      lastPrice: snapshot.lastPrice,
      bestBid: snapshot.bestBid,
      bestAsk: snapshot.bestAsk,
      bidDepth: snapshot.bidDepth,
      askDepth: snapshot.askDepth,
      volume: snapshot.volume,
      totalTurnover: snapshot.totalTurnover,
      metadata: {},
      createdAt: snapshot.timestamp
    };
  }

  private toDbCandle(candle: Candle) {
    return {
      id: `candle-${candle.ticker}-5m-${candle.timestamp}`,
      ticker: candle.ticker,
      timeframe: '5m',
      candleTime: candle.timestamp,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: candle.volume,
      vwap: candle.vwap,
      metadata: {},
      createdAt: candle.timestamp
    };
  }

  private toDbSignal(signal: Signal): DbSignal {
    const [entryZoneLow, entryZoneHigh] = signal.entryZone;

    return {
      id: signal.id,
      ticker: signal.ticker,
      strategy: signal.strategy,
      direction: signal.type,
      status: signal.status,
      entryZoneLow,
      entryZoneHigh,
      stopLoss: signal.stopLoss,
      target1: signal.targets[0],
      target2: signal.targets[1],
      confidence: this.optionalNumberFeature(signal, 'confidence'),
      validUntil: signal.validUntil,
      features: this.toJsonObject(signal.features),
      statusReason: signal.statusReason,
      latestPrice: signal.latestPrice,
      maxFavorableMovePercent: signal.maxFavorableMovePercent,
      maxAdverseMovePercent: signal.maxAdverseMovePercent,
      createdAt: signal.timestamp,
      updatedAt: signal.lastCheckedAt ?? signal.timestamp
    };
  }

  private toDbSignalEvent(event: SignalEvent): DbSignalEvent {
    return {
      id: event.id,
      signalId: event.signalId,
      previousStatus: event.previousStatus,
      newStatus: event.newStatus,
      reason: event.reason,
      latestPrice: event.latestPrice,
      eventTime: event.timestamp,
      createdAt: event.timestamp
    };
  }

  private toDbSignalOutcome(outcome: SignalOutcome, signal: Signal): DbSignalOutcome {
    return {
      id: `outcome-${outcome.signalId}`,
      signalId: outcome.signalId,
      ticker: signal.ticker,
      strategy: signal.strategy,
      finalStatus: outcome.finalStatus,
      entryPrice: outcome.entryPrice,
      exitPrice: outcome.exitPrice,
      returnPercent: outcome.returnPercent,
      maxFavorableMovePercent: outcome.maxFavorableMovePercent,
      maxAdverseMovePercent: outcome.maxAdverseMovePercent,
      openedAt: outcome.openedAt,
      closedAt: outcome.closedAt,
      closeReason: outcome.closeReason,
      createdAt: outcome.closedAt
    };
  }

  private entryPrice(signal: Signal): number {
    const [low, high] = signal.entryZone;
    return (low + high) / 2;
  }

  private returnPercent(signal: Signal, entryPrice: number, exitPrice: number): number {
    if (entryPrice <= 0) return 0;

    const rawReturn = ((exitPrice - entryPrice) / entryPrice) * 100;
    return signal.type === 'SELL' || signal.type === 'SELL_WATCH' ? -rawReturn : rawReturn;
  }

  private optionalNumberFeature(signal: Signal, key: string): number | undefined {
    const value = signal.features[key];
    return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
  }

  private toJsonObject(value: Record<string, unknown>): JsonObject {
    return JSON.parse(JSON.stringify(value)) as JsonObject;
  }

  private signalId(ticker: string, strategy: string, timestamp: number): string {
    return `${ticker}-${strategy}-${timestamp}`.replace(/[^a-zA-Z0-9_-]/g, '-');
  }
}
