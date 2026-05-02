export interface MarketSnapshot {
  ticker: string;
  timestamp: number;
  lastPrice: number;
  bestBid: number;
  bestAsk: number;
  bidDepth: number;
  askDepth: number;
  volume: number;
  totalTurnover: number;
}

export interface Candle {
  ticker: string;
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number;
}

export interface Signal {
  id: string;
  ticker: string;
  strategy: string;
  timestamp: number;
  type: 'BUY_WATCH' | 'SELL_WATCH' | 'BUY' | 'SELL';
  entryZone: [number, number];
  stopLoss: number;
  targets: number[];
  validUntil: number;
  features: Record<string, any>;
  status: SignalStatus;
  maxFavorableMovePercent?: number;
  maxAdverseMovePercent?: number;
  latestPrice?: number;
  lastCheckedAt?: number;
  statusReason?: string;
}

export type SignalStatus =
  | 'ACTIVE'
  | 'EXPIRED'
  | 'INVALIDATED'
  | 'TARGET_HIT'
  | 'STOP_HIT'
  | 'ENDED';

export interface SignalOutcome {
  signalId: string;
  maxFavorableMove: number;
  maxAdverseMove: number;
  outcome5m: string;
  outcome15m: string;
  outcome1h: string;
  eodOutcome: string;
}

export interface StrategyPipeline {
  run(snapshot: MarketSnapshot): Promise<Signal | null>;
}

export interface ScannerAgent {
  scan(snapshots: MarketSnapshot[]): Promise<MarketSnapshot[]>;
}

export interface CandleAgent {
  process(snapshot: MarketSnapshot): Candle | null;
  getCandles(ticker: string): Candle[];
}

export interface IndicatorAgent {
  calculateVWAP(candles: Candle[]): number;
  calculateSpreadPercent(bid: number, ask: number): number;
  calculateVolumeRatio(currentVolume: number, averageVolume: number): number;
  calculateOrderBookImbalance(bidDepth: number, askDepth: number): number;
}

export interface SetupDetectorAgent {
  detect(snapshot: MarketSnapshot, candles: Candle[], indicators: any): Promise<Partial<Signal> | null>;
}

export interface RiskValidatorAgent {
  validate(setup: Partial<Signal>, snapshot: MarketSnapshot): Promise<boolean>;
}

export interface SignalAgent {
  generate(setup: Partial<Signal>): Signal;
}

export interface MonitorAgent {
  monitor(signal: Signal, snapshot: MarketSnapshot): Promise<Signal>;
}

export interface MemoryAgent {
  saveSignal(signal: Signal): Promise<void>;
  updateSignalOutcome(outcome: SignalOutcome): Promise<void>;
  getSignal(id: string): Promise<Signal | null>;
}
