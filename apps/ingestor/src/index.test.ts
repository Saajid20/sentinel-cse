import { describe, expect, it, vi } from 'vitest';
import { printMockSnapshots, runMockIngestor } from './index.js';

describe('mock ingestor entrypoint', () => {
  it('observes a small watchlist once', async () => {
    const result = await runMockIngestor([
      {
        ticker: 'SAMP.N0000',
        enabled: true,
        source: 'test'
      },
      {
        ticker: 'DISABLED.N0000',
        enabled: false,
        source: 'test'
      }
    ]);

    expect(result.watchlist).toHaveLength(2);
    expect(result.snapshots).toHaveLength(1);
    expect(result.snapshots[0]?.ticker).toBe('SAMP.N0000');
  });

  it('prints and returns mock snapshots', async () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);

    const snapshots = await printMockSnapshots();

    expect(snapshots).toHaveLength(2);
    expect(log).toHaveBeenCalledOnce();

    log.mockRestore();
  });
});
