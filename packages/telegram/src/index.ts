import { Signal, SignalOutcome } from '@sentinel/core';

export interface TelegramAlertMessage {
  id: string;
  signalId?: string;
  ticker?: string;
  kind:
    | 'BUY_WATCH'
    | 'ACTIVE_UPDATE'
    | 'EXPIRED_UPDATE'
    | 'INVALIDATED_UPDATE'
    | 'TARGET_HIT_UPDATE'
    | 'STOP_HIT_UPDATE'
    | 'EOD_SUMMARY_DRAFT';
  text: string;
  createdAt: number;
}

export class TelegramAlertFormatter {
  formatBuyWatch(signal: Signal): TelegramAlertMessage {
    const target1 = signal.targets[0];
    const target2 = signal.targets[1];
    const latestPrice = signal.latestPrice ?? this.numberFeature(signal, 'latestPrice');

    return this.message(signal, 'BUY_WATCH', [
      `BUY WATCH: ${signal.ticker}`,
      `Strategy: ${signal.strategy}`,
      `Entry zone: ${this.formatRange(signal.entryZone)}`,
      `Stop loss: ${this.formatNumber(signal.stopLoss)}`,
      `Target 1: ${this.formatOptionalNumber(target1)}`,
      `Target 2: ${this.formatOptionalNumber(target2)}`,
      `Confidence: ${this.formatConfidence(signal)}`,
      `Valid until: ${this.formatTimestamp(signal.validUntil)}`,
      `Reasons: ${this.formatReasons(signal)}`,
      `Invalidation rules: price below VWAP; spread above 2%; price leaves entry zone before entry`,
      `Latest price: ${this.formatOptionalNumber(latestPrice)}`
    ]);
  }

  formatSignalUpdate(signal: Signal): TelegramAlertMessage {
    switch (signal.status) {
      case 'ACTIVE':
        return this.formatActiveUpdate(signal);
      case 'EXPIRED':
        return this.formatExpiredUpdate(signal);
      case 'INVALIDATED':
        return this.formatInvalidatedUpdate(signal);
      case 'TARGET_HIT':
        return this.formatTargetHitUpdate(signal);
      case 'STOP_HIT':
        return this.formatStopHitUpdate(signal);
      case 'ENDED':
        return this.message(signal, 'EOD_SUMMARY_DRAFT', this.lifecycleLines(signal, 'ENDED'));
    }
  }

  formatActiveUpdate(signal: Signal): TelegramAlertMessage {
    return this.message(signal, 'ACTIVE_UPDATE', this.lifecycleLines(signal, 'ACTIVE'));
  }

  formatExpiredUpdate(signal: Signal): TelegramAlertMessage {
    return this.message(signal, 'EXPIRED_UPDATE', this.lifecycleLines(signal, 'EXPIRED'));
  }

  formatInvalidatedUpdate(signal: Signal): TelegramAlertMessage {
    return this.message(signal, 'INVALIDATED_UPDATE', this.lifecycleLines(signal, 'INVALIDATED'));
  }

  formatTargetHitUpdate(signal: Signal): TelegramAlertMessage {
    return this.message(signal, 'TARGET_HIT_UPDATE', this.lifecycleLines(signal, 'TARGET HIT'));
  }

  formatStopHitUpdate(signal: Signal): TelegramAlertMessage {
    return this.message(signal, 'STOP_HIT_UPDATE', this.lifecycleLines(signal, 'STOP HIT'));
  }

  formatEndOfDaySummaryDraft(outcomes: SignalOutcome[], createdAt: number = Date.now()): TelegramAlertMessage {
    const totalReturn = outcomes.reduce((sum, outcome) => sum + outcome.returnPercent, 0);
    const lines = [
      'End-of-day summary draft',
      `Signals closed: ${outcomes.length}`,
      `Combined return: ${this.formatPercent(totalReturn)}`,
      ...outcomes.map(
        (outcome) =>
          `${outcome.signalId}: ${outcome.finalStatus}, return ${this.formatPercent(outcome.returnPercent)}, reason ${outcome.closeReason}`
      )
    ];

    return {
      id: `telegram-eod-${createdAt}`,
      kind: 'EOD_SUMMARY_DRAFT',
      text: lines.join('\n'),
      createdAt
    };
  }

  private lifecycleLines(signal: Signal, label: string): string[] {
    return [
      `${label}: ${signal.ticker}`,
      `Strategy: ${signal.strategy}`,
      `Status reason: ${signal.statusReason ?? 'No reason provided'}`,
      `Latest price: ${this.formatOptionalNumber(signal.latestPrice)}`,
      `Last checked: ${this.formatOptionalTimestamp(signal.lastCheckedAt)}`,
      `Max favorable move: ${this.formatOptionalPercent(signal.maxFavorableMovePercent)}`,
      `Max adverse move: ${this.formatOptionalPercent(signal.maxAdverseMovePercent)}`
    ];
  }

  private message(signal: Signal, kind: TelegramAlertMessage['kind'], lines: string[]): TelegramAlertMessage {
    return {
      id: `telegram-${signal.id}-${kind}-${signal.lastCheckedAt ?? signal.timestamp}`,
      signalId: signal.id,
      ticker: signal.ticker,
      kind,
      text: lines.join('\n'),
      createdAt: signal.lastCheckedAt ?? signal.timestamp
    };
  }

  private formatReasons(signal: Signal): string {
    const reasons = signal.features['reasons'];
    if (Array.isArray(reasons) && reasons.length > 0) {
      return reasons.map(String).join('; ');
    }

    return 'price above VWAP; break of first 5-minute high; volume, spread, and depth checks passed';
  }

  private formatConfidence(signal: Signal): string {
    const confidence = signal.features['confidence'];
    if (typeof confidence === 'number' && Number.isFinite(confidence)) {
      return this.formatPercent(confidence);
    }

    return 'not scored';
  }

  private numberFeature(signal: Signal, key: string): number | undefined {
    const value = signal.features[key];
    return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
  }

  private formatRange([low, high]: [number, number]): string {
    return `${this.formatNumber(low)} - ${this.formatNumber(high)}`;
  }

  private formatOptionalNumber(value: number | undefined): string {
    return value === undefined ? 'n/a' : this.formatNumber(value);
  }

  private formatNumber(value: number): string {
    return value.toFixed(2);
  }

  private formatOptionalPercent(value: number | undefined): string {
    return value === undefined ? 'n/a' : this.formatPercent(value);
  }

  private formatPercent(value: number): string {
    return `${value.toFixed(2)}%`;
  }

  private formatOptionalTimestamp(value: number | undefined): string {
    return value === undefined ? 'n/a' : this.formatTimestamp(value);
  }

  private formatTimestamp(value: number): string {
    return new Date(value).toISOString();
  }
}

export class MockTelegramAlertSender {
  private sentMessages: TelegramAlertMessage[] = [];

  async send(message: TelegramAlertMessage): Promise<void> {
    this.sentMessages.push({ ...message });
  }

  listSentMessages(): TelegramAlertMessage[] {
    return this.sentMessages.map((message) => ({ ...message }));
  }

  clear(): void {
    this.sentMessages = [];
  }
}
