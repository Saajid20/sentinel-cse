import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  ATRAD_PERSISTENT_PROFILE_PATH,
  ATRAD_STORAGE_STATE_PATH,
  createManualATradLoginConfig,
  DEFAULT_ATRAD_BASE_URL,
  formatManualATradLoginInstructions,
  isSafePersistentProfilePath,
  isSafeStorageStatePath,
  ManualATradLoginRuntime,
  runManualATradLogin
} from './manualATradLogin.js';

describe('manual ATrad login script helpers', () => {
  it('uses safe default config without environment variables', () => {
    const config = createManualATradLoginConfig();

    expect(config).toEqual({
      baseUrl: new URL(DEFAULT_ATRAD_BASE_URL).toString(),
      storageStatePath: ATRAD_STORAGE_STATE_PATH,
      persistentProfilePath: ATRAD_PERSISTENT_PROFILE_PATH,
      persistentProfile: false,
      headless: false,
      readonlyMode: true
    });
  });

  it('accepts a base URL from CLI args', () => {
    const config = createManualATradLoginConfig(['--base-url', 'https://example.invalid/login']);

    expect(config.baseUrl).toBe('https://example.invalid/login');
  });

  it('parses the persistent profile flag', () => {
    const config = createManualATradLoginConfig(['--persistent-profile']);

    expect(config.persistentProfile).toBe(true);
    expect(config.persistentProfilePath).toBe(ATRAD_PERSISTENT_PROFILE_PATH);
  });

  it('keeps the storage state path constrained to the ignored local auth path', () => {
    const gitignore = readFileSync('.gitignore', 'utf8');

    expect(ATRAD_STORAGE_STATE_PATH).toBe('playwright/.auth/atrad-storage-state.json');
    expect(ATRAD_PERSISTENT_PROFILE_PATH).toBe('playwright/.profiles/atrad');
    expect(isSafeStorageStatePath(ATRAD_STORAGE_STATE_PATH)).toBe(true);
    expect(isSafePersistentProfilePath(ATRAD_PERSISTENT_PROFILE_PATH)).toBe(true);
    expect(isSafeStorageStatePath('storageState.json')).toBe(false);
    expect(isSafePersistentProfilePath('playwright/.profiles/other')).toBe(false);
    expect(gitignore).toContain('playwright/.auth/');
    expect(gitignore).toContain('playwright/.auth/*');
    expect(gitignore).toContain('playwright/.profiles/');
    expect(gitignore).toContain('playwright/.profiles/*');
    expect(gitignore).toContain('**/.profiles/');
    expect(gitignore).toContain('**/storageState.json');
    expect(gitignore).toContain('*.auth.json');
  });

  it('prints manual login and 2FA instructions', () => {
    const instructions = formatManualATradLoginInstructions(createManualATradLoginConfig());

    expect(instructions).toContain(
      'Log in manually, complete 2FA if needed, then return to this terminal and press Enter.'
    );
    expect(instructions.join('\n')).toContain(ATRAD_STORAGE_STATE_PATH);
  });

  it('can run with injected browser primitives without launching a real browser', async () => {
    const calls: string[] = [];
    const runtime: ManualATradLoginRuntime = {
      async launchSession() {
        calls.push('launch-ephemeral');
        return {
          session: {
            pages() {
              return [];
            },
            async newPage() {
              calls.push('new-page');
              return {
                async goto(url: string) {
                  calls.push(`goto:${url}`);
                }
              };
            },
            async storageState(options: { path: string }) {
              calls.push(`storage:${options.path}`);
            }
          },
          async close() {
            calls.push('close');
          }
        };
      },
      async waitForUser() {
        calls.push('wait');
      },
      log(message: string) {
        calls.push(`log:${message}`);
      }
    };

    const path = await runManualATradLogin(createManualATradLoginConfig(), runtime);

    expect(path).toBe(ATRAD_STORAGE_STATE_PATH);
    expect(calls).toEqual(
      expect.arrayContaining([
        'launch-ephemeral',
        'new-page',
        `goto:${new URL(DEFAULT_ATRAD_BASE_URL).toString()}`,
        'wait',
        `storage:${ATRAD_STORAGE_STATE_PATH}`,
        'close'
      ])
    );
  });

  it('uses the persistent profile runtime path when the flag is present', async () => {
    const calls: string[] = [];
    const runtime: ManualATradLoginRuntime = {
      async launchSession(config) {
        calls.push(config.persistentProfile ? 'launch-persistent' : 'launch-ephemeral');
        return {
          session: {
            pages() {
              return [];
            },
            async newPage() {
              calls.push('new-page');
              return {
                async goto(url: string) {
                  calls.push(`goto:${url}`);
                }
              };
            },
            async storageState(options: { path: string }) {
              calls.push(`storage:${options.path}`);
            }
          },
          async close() {
            calls.push('close');
          }
        };
      },
      async waitForUser() {
        calls.push('wait');
      },
      log(message: string) {
        calls.push(`log:${message}`);
      }
    };

    const config = createManualATradLoginConfig(['--persistent-profile']);
    const path = await runManualATradLogin(config, runtime);

    expect(path).toBe(ATRAD_PERSISTENT_PROFILE_PATH);
    expect(calls).toEqual(
      expect.arrayContaining([
        'launch-persistent',
        'new-page',
        `goto:${new URL(DEFAULT_ATRAD_BASE_URL).toString()}`,
        'wait',
        `storage:${ATRAD_STORAGE_STATE_PATH}`,
        'close'
      ])
    );
  });

  it('does not read credentials, environment variables, or include order action strings', () => {
    const source = readFileSync('scripts/manualATradLogin.ts', 'utf8');

    expect(source).not.toMatch(/process\.env/);
    expect(source).not.toMatch(/username|password/i);
    expect(source).not.toMatch(/buy|sell|submit|confirm|quantity|price input|market order|limit order/i);
  });
});
