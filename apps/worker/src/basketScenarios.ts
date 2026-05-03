import { MarketSnapshot } from '@sentinel/core';

export interface BasketReplayScenario {
  name: string;
  snapshots: MarketSnapshot[];
  averageVolumeByTicker?: Record<string, number>;
  notes?: string[];
}

const defaultTicker = 'SAMP.N0000';
const otherTicker = 'OTHER.N0000';

const snapshot = (overrides: Partial<MarketSnapshot>): MarketSnapshot => ({
  ticker: defaultTicker,
  timestamp: 0,
  lastPrice: 50,
  bestBid: 49.5,
  bestAsk: 50,
  bidDepth: 1_000,
  askDepth: 800,
  volume: 100,
  totalTurnover: 5_000,
  ...overrides
});

const openingBuildSnapshots = (ticker: string = defaultTicker, offset = 0): MarketSnapshot[] => [
  snapshot({ ticker, timestamp: offset, lastPrice: 50, volume: 100, totalTurnover: 5_000 }),
  snapshot({ ticker, timestamp: offset + 60_000, lastPrice: 52, volume: 50, totalTurnover: 2_600 }),
  snapshot({ ticker, timestamp: offset + 300_000, lastPrice: 52, volume: 0, totalTurnover: 0 })
];

const qualifyingSignalSnapshot = (
  overrides: Partial<MarketSnapshot> = {},
  ticker: string = defaultTicker,
  offset = 0
): MarketSnapshot =>
  snapshot({
    ticker,
    timestamp: offset + 301_000,
    lastPrice: 55,
    bestBid: 54.5,
    bestAsk: 55,
    bidDepth: 2_000,
    askDepth: 1_000,
    volume: 300,
    totalTurnover: 16_500,
    ...overrides
  });

const baseScenario = (...tail: MarketSnapshot[]): MarketSnapshot[] => [
  ...openingBuildSnapshots(),
  qualifyingSignalSnapshot(),
  ...tail
];

export const basketReplayScenarios: BasketReplayScenario[] = [
  {
    name: 'target hit',
    snapshots: baseScenario(
      snapshot({ timestamp: 361_000, lastPrice: 58, bestBid: 57.5, bestAsk: 58, volume: 50 })
    )
  },
  {
    name: 'stop hit',
    snapshots: baseScenario(
      snapshot({ timestamp: 361_000, lastPrice: 50, bestBid: 49.8, bestAsk: 50, volume: 50 })
    )
  },
  {
    name: 'expired',
    snapshots: baseScenario(
      snapshot({ timestamp: 901_001, lastPrice: 55, bestBid: 54.5, bestAsk: 55, volume: 50 })
    )
  },
  {
    name: 'invalidated by spread widening',
    snapshots: baseScenario(
      snapshot({ timestamp: 361_000, lastPrice: 55, bestBid: 53, bestAsk: 55, volume: 50 })
    )
  },
  {
    name: 'invalidated by price below VWAP',
    snapshots: baseScenario(
      snapshot({ timestamp: 361_000, lastPrice: 51, bestBid: 50.8, bestAsk: 51.1, volume: 50 })
    )
  },
  {
    name: 'no signal because spread too high',
    snapshots: [
      ...openingBuildSnapshots(),
      qualifyingSignalSnapshot({ bestBid: 53, bestAsk: 55 })
    ]
  },
  {
    name: 'no signal because volume ratio too low',
    snapshots: [
      ...openingBuildSnapshots(),
      qualifyingSignalSnapshot({ volume: 150, totalTurnover: 8_250 })
    ]
  },
  {
    name: 'no signal because bid/ask imbalance weak',
    snapshots: [
      ...openingBuildSnapshots(),
      qualifyingSignalSnapshot({ bidDepth: 900, askDepth: 1_000 })
    ]
  },
  {
    name: 'strong winner',
    snapshots: baseScenario(
      snapshot({ timestamp: 361_000, lastPrice: 61, bestBid: 60.5, bestAsk: 61, volume: 80 })
    )
  },
  {
    name: 'weak winner',
    snapshots: baseScenario(
      snapshot({ timestamp: 361_000, lastPrice: 57.8, bestBid: 57.3, bestAsk: 57.8, volume: 40 })
    )
  },
  {
    name: 'false breakout',
    snapshots: [
      ...openingBuildSnapshots(),
      qualifyingSignalSnapshot({ volume: 210, totalTurnover: 11_550 }),
      snapshot({ timestamp: 361_000, lastPrice: 50, bestBid: 49.8, bestAsk: 50, volume: 80 })
    ],
    notes: ['Generated with a low-but-passing volume ratio, then hit stop.']
  },
  {
    name: 'multi-ticker mixed session',
    snapshots: [
      ...openingBuildSnapshots(defaultTicker, 0),
      ...openingBuildSnapshots(otherTicker, 10_000),
      qualifyingSignalSnapshot({}, defaultTicker, 0),
      qualifyingSignalSnapshot({ volume: 150, totalTurnover: 8_250 }, otherTicker, 10_000),
      snapshot({ ticker: defaultTicker, timestamp: 361_000, lastPrice: 58, bestBid: 57.5, bestAsk: 58, volume: 50 })
    ],
    averageVolumeByTicker: {
      [defaultTicker]: 100,
      [otherTicker]: 100
    }
  }
];

export function averageVolumeByTickerForScenario(scenario: BasketReplayScenario): Record<string, number> {
  if (scenario.averageVolumeByTicker) return { ...scenario.averageVolumeByTicker };

  return Object.fromEntries([...new Set(scenario.snapshots.map((snapshot) => snapshot.ticker))].map((ticker) => [ticker, 100]));
}
