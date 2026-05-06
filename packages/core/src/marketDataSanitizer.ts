import {
  MarketDataSanitizationIssue,
  MarketDataSanitizationIssueCode,
  MarketDataSanitizerConfig,
  MarketSnapshot,
  RawMarketSnapshot,
  RawMarketSnapshotValue,
  SanitizedMarketSnapshotResult
} from './types.js';

export const DEFAULT_MARKET_DATA_SANITIZER_CONFIG: MarketDataSanitizerConfig = {
  maxSpreadPercent: 5,
  maxPriceMovePercentPerTick: 20,
  allowZeroDepth: false,
  staleTimestampToleranceMs: 0
};

export class MarketDataSanitizer {
  private readonly config: MarketDataSanitizerConfig;
  private readonly lastAcceptedSnapshots = new Map<string, MarketSnapshot>();

  constructor(config: Partial<MarketDataSanitizerConfig> = {}) {
    this.config = {
      ...DEFAULT_MARKET_DATA_SANITIZER_CONFIG,
      ...config
    };
  }

  sanitize(raw: RawMarketSnapshot): SanitizedMarketSnapshotResult {
    const issues: MarketDataSanitizationIssue[] = [];
    const warnings: MarketDataSanitizationIssue[] = [];
    const issueSource = raw.source ?? this.config.source;

    const ticker = this.normalizeTicker(raw.ticker);
    if (!ticker) {
      issues.push(this.issue('MISSING_TICKER', 'Ticker is required.', 'ticker', raw.ticker, issueSource));
    }

    const timestamp = this.parseNumber(raw.timestamp);
    if (timestamp === undefined || timestamp < 0) {
      issues.push(this.issue('INVALID_TIMESTAMP', 'Timestamp must be a non-negative number.', 'timestamp', raw.timestamp, issueSource));
    }

    const lastPrice = this.parseNumber(raw.lastPrice);
    if (lastPrice === undefined || lastPrice <= 0) {
      issues.push(this.issue('INVALID_LAST_PRICE', 'Last price must be greater than zero.', 'lastPrice', raw.lastPrice, issueSource));
    }

    const bestBid = this.parseNumber(raw.bestBid);
    const bestAsk = this.parseNumber(raw.bestAsk);
    if (
      bestBid === undefined ||
      bestAsk === undefined ||
      bestBid <= 0 ||
      bestAsk <= 0
    ) {
      issues.push(this.issue('INVALID_BID_ASK', 'Best bid and ask must be greater than zero.', undefined, raw.bestBid ?? raw.bestAsk, issueSource));
    } else if (bestBid > bestAsk) {
      issues.push(this.issue('BID_GREATER_THAN_ASK', 'Best bid cannot be greater than best ask.', undefined, `${bestBid}/${bestAsk}`, issueSource));
    }

    const bidDepth = this.parseNumber(raw.bidDepth);
    const askDepth = this.parseNumber(raw.askDepth);
    if (!this.isValidDepth(bidDepth) || !this.isValidDepth(askDepth)) {
      issues.push(this.issue('INVALID_DEPTH', 'Bid depth and ask depth must be valid non-negative numbers.', undefined, raw.bidDepth ?? raw.askDepth, issueSource));
    }

    const volume = this.parseNumber(raw.volume);
    if (volume === undefined || volume < 0) {
      issues.push(this.issue('INVALID_VOLUME', 'Volume must be a valid non-negative number.', 'volume', raw.volume, issueSource));
    }

    if (issues.length > 0 || !ticker || timestamp === undefined || lastPrice === undefined || bestBid === undefined || bestAsk === undefined || bidDepth === undefined || askDepth === undefined || volume === undefined) {
      return this.rejected(issues, warnings);
    }

    const totalTurnover = this.parseNumber(raw.totalTurnover);
    const snapshot: MarketSnapshot = {
      ticker,
      timestamp,
      lastPrice,
      bestBid,
      bestAsk,
      bidDepth,
      askDepth,
      volume,
      totalTurnover: totalTurnover !== undefined && totalTurnover >= 0 ? totalTurnover : lastPrice * volume
    };

    const spreadPercent = this.calculateSpreadPercent(snapshot.bestBid, snapshot.bestAsk);
    if (spreadPercent > this.config.maxSpreadPercent) {
      issues.push(
        this.issue(
          'UNREALISTIC_SPREAD',
          `Spread ${spreadPercent.toFixed(2)}% exceeds configured maximum ${this.config.maxSpreadPercent.toFixed(2)}%.`,
          'bestBid/bestAsk',
          `${snapshot.bestBid}/${snapshot.bestAsk}`,
          issueSource
        )
      );
    }

    const previousSnapshot = this.lastAcceptedSnapshots.get(snapshot.ticker);
    if (previousSnapshot) {
      if (this.isDuplicateSnapshot(previousSnapshot, snapshot)) {
        issues.push(this.issue('DUPLICATE_SNAPSHOT', 'Snapshot matches the last accepted snapshot for this ticker.', 'ticker', snapshot.ticker, issueSource));
      }

      const staleCutoff = previousSnapshot.timestamp - (this.config.staleTimestampToleranceMs ?? 0);
      if (snapshot.timestamp < staleCutoff) {
        issues.push(
          this.issue(
            'STALE_TIMESTAMP',
            `Snapshot timestamp ${snapshot.timestamp} is older than the last accepted timestamp ${previousSnapshot.timestamp}.`,
            'timestamp',
            raw.timestamp,
            issueSource
          )
        );
      }

      const priceMovePercent = this.calculatePriceMovePercent(previousSnapshot.lastPrice, snapshot.lastPrice);
      if (priceMovePercent > this.config.maxPriceMovePercentPerTick) {
        issues.push(
          this.issue(
            'OUTLIER_PRICE_MOVE',
            `Price move ${priceMovePercent.toFixed(2)}% exceeds configured maximum ${this.config.maxPriceMovePercentPerTick.toFixed(2)}%.`,
            'lastPrice',
            raw.lastPrice,
            issueSource
          )
        );
      }
    }

    if (issues.length > 0) {
      return this.rejected(issues, warnings);
    }

    this.lastAcceptedSnapshots.set(snapshot.ticker, { ...snapshot });

    return {
      accepted: true,
      snapshot,
      issues,
      warnings
    };
  }

  reset(): void {
    this.lastAcceptedSnapshots.clear();
  }

  getLastAcceptedSnapshot(ticker: string): MarketSnapshot | undefined {
    const snapshot = this.lastAcceptedSnapshots.get(this.normalizeTicker(ticker) ?? ticker);
    return snapshot ? { ...snapshot } : undefined;
  }

  private normalizeTicker(value: RawMarketSnapshotValue): string | undefined {
    if (typeof value !== 'string') return undefined;

    const ticker = value.trim().toUpperCase();
    return ticker.length > 0 ? ticker : undefined;
  }

  private parseNumber(value: RawMarketSnapshotValue): number | undefined {
    if (typeof value === 'number') {
      return Number.isFinite(value) ? value : undefined;
    }

    if (typeof value !== 'string') return undefined;

    const normalized = value.trim().replace(/,/g, '');
    if (normalized.length === 0) return undefined;

    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  private isValidDepth(depth: number | undefined): depth is number {
    if (depth === undefined || depth < 0) return false;
    if (this.config.allowZeroDepth) return true;
    return depth > 0;
  }

  private calculateSpreadPercent(bestBid: number, bestAsk: number): number {
    if (bestAsk <= 0) return Number.POSITIVE_INFINITY;
    return ((bestAsk - bestBid) / bestAsk) * 100;
  }

  private calculatePriceMovePercent(previousPrice: number, currentPrice: number): number {
    if (previousPrice <= 0) return Number.POSITIVE_INFINITY;
    return Math.abs(((currentPrice - previousPrice) / previousPrice) * 100);
  }

  private isDuplicateSnapshot(previous: MarketSnapshot, current: MarketSnapshot): boolean {
    return (
      previous.ticker === current.ticker &&
      previous.timestamp === current.timestamp &&
      previous.lastPrice === current.lastPrice &&
      previous.bestBid === current.bestBid &&
      previous.bestAsk === current.bestAsk &&
      previous.bidDepth === current.bidDepth &&
      previous.askDepth === current.askDepth &&
      previous.volume === current.volume &&
      previous.totalTurnover === current.totalTurnover
    );
  }

  private issue(
    code: MarketDataSanitizationIssueCode,
    message: string,
    field?: string,
    value?: RawMarketSnapshotValue,
    source?: string
  ): MarketDataSanitizationIssue {
    return {
      code,
      message,
      field,
      value,
      source
    };
  }

  private rejected(
    issues: MarketDataSanitizationIssue[],
    warnings: MarketDataSanitizationIssue[]
  ): SanitizedMarketSnapshotResult {
    return {
      accepted: false,
      issues,
      warnings
    };
  }
}
