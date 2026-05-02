import { MarketSnapshot } from '@sentinel/core';

const ticker = 'SAMP.N0000';

const snapshot = (overrides: Partial<MarketSnapshot>): MarketSnapshot => ({
  ticker,
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

const openingBuildSnapshots = (): MarketSnapshot[] => [
  snapshot({ timestamp: 0, lastPrice: 50, volume: 100, totalTurnover: 5_000 }),
  snapshot({ timestamp: 60_000, lastPrice: 52, volume: 50, totalTurnover: 2_600 }),
  snapshot({ timestamp: 300_000, lastPrice: 52, volume: 0, totalTurnover: 0 })
];

const qualifyingSignalSnapshot = (): MarketSnapshot =>
  snapshot({
    timestamp: 301_000,
    lastPrice: 55,
    bestBid: 54.5,
    bestAsk: 55,
    bidDepth: 2_000,
    askDepth: 1_000,
    volume: 300,
    totalTurnover: 16_500
  });

export const replayScenarios = {
  openingMomentumTargetHit: (): MarketSnapshot[] => [
    ...openingBuildSnapshots(),
    qualifyingSignalSnapshot(),
    snapshot({
      timestamp: 361_000,
      lastPrice: 58,
      bestBid: 57.5,
      bestAsk: 58,
      bidDepth: 1_500,
      askDepth: 1_000,
      volume: 50,
      totalTurnover: 2_900
    })
  ],

  openingMomentumExpired: (): MarketSnapshot[] => [
    ...openingBuildSnapshots(),
    qualifyingSignalSnapshot(),
    snapshot({
      timestamp: 901_001,
      lastPrice: 55,
      bestBid: 54.5,
      bestAsk: 55,
      bidDepth: 1_500,
      askDepth: 1_000,
      volume: 50,
      totalTurnover: 2_750
    })
  ],

  openingMomentumInvalidatedBySpread: (): MarketSnapshot[] => [
    ...openingBuildSnapshots(),
    qualifyingSignalSnapshot(),
    snapshot({
      timestamp: 361_000,
      lastPrice: 55,
      bestBid: 53,
      bestAsk: 55,
      bidDepth: 1_500,
      askDepth: 1_000,
      volume: 50,
      totalTurnover: 2_750
    })
  ],

  failedRiskChecks: (): MarketSnapshot[] => [
    ...openingBuildSnapshots(),
    snapshot({
      timestamp: 301_000,
      lastPrice: 55,
      bestBid: 53,
      bestAsk: 55,
      bidDepth: 2_000,
      askDepth: 1_000,
      volume: 300,
      totalTurnover: 16_500
    })
  ],

  multiTickerOutOfOrder: (): MarketSnapshot[] => [
    { ...qualifyingSignalSnapshot(), timestamp: 301_000 },
    snapshot({ timestamp: 0, lastPrice: 50, volume: 100 }),
    snapshot({ ticker: 'OTHER.N0000', timestamp: 10_000, lastPrice: 20 }),
    snapshot({ timestamp: 60_000, lastPrice: 52, volume: 50 }),
    snapshot({ timestamp: 300_000, lastPrice: 52, volume: 0 })
  ]
};
