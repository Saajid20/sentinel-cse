import { describe, expect, it } from 'vitest';
import { runSentinelCommand } from './sentinel.js';

describe('sentinel operator console', () => {
  it('prints help output', async () => {
    const result = await runSentinelCommand(['help']);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('pnpm sentinel status');
    expect(result.output).toContain('pnpm sentinel atrad-login');
    expect(result.output).toContain('pnpm sentinel atrad-login-and-observe');
    expect(result.output).toContain('pnpm sentinel atrad-observe-once');
    expect(result.output).toContain('pnpm sentinel atrad-record-session');
    expect(result.output).toContain('telegram-test');
    expect(result.output).toContain('supabase-test');
  });

  it('prints status output', async () => {
    const result = await runSentinelCommand(['status']);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('Sentinel-CSE v0.1 operator console');
    expect(result.output).toContain('signal-only paper-trading');
    expect(result.output).toContain('default runtime mode: SHADOW');
    expect(result.output).toContain('PAPER_ALERT mode available only when explicitly configured');
    expect(result.output).toContain('auto-trading disabled');
    expect(result.output).toContain('ATrad live connection disabled');
  });

  it('returns an error for unknown commands', async () => {
    const result = await runSentinelCommand(['unknown']);

    expect(result.exitCode).toBe(1);
    expect(result.error).toBe('Unknown Sentinel command: unknown');
    expect(result.output).toContain('Sentinel-CSE operator console');
  });

  it('formats the basket command summary without external services', async () => {
    const result = await runSentinelCommand(['basket']);

    expect(result.exitCode).toBe(0);
    expect(result.output).toContain('Sentinel-CSE mock basket replay summary');
    expect(result.output).toContain('Scenarios processed: 12');
    expect(result.output).toContain('Signals generated:');
    expect(result.output).toContain('Profit factor:');
    expect(result.output).toContain('Recommendations:');
  });
});
