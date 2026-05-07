import { mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { pathToFileURL } from 'node:url';
import { stdin as input, stdout as output } from 'node:process';
import { chromium, type BrowserContext } from 'playwright';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';

export const DEFAULT_ATRAD_BASE_URL = 'https://example.invalid/atrad-login';
export const ATRAD_STORAGE_STATE_PATH = 'playwright/.auth/atrad-storage-state.json';
export const ATRAD_PERSISTENT_PROFILE_PATH = 'playwright/.profiles/atrad';

export interface ManualATradLoginConfig {
  baseUrl: string;
  storageStatePath: string;
  persistentProfilePath: string;
  persistentProfile: boolean;
  headless: false;
  readonlyMode: true;
}

export interface ManualATradLoginPageLike {
  goto(url: string, options: { waitUntil: 'domcontentloaded' }): Promise<void>;
}

export interface ManualATradLoginSessionLike {
  pages(): ManualATradLoginPageLike[];
  newPage(): Promise<ManualATradLoginPageLike>;
  storageState(options: { path: string }): Promise<void>;
}

export interface ManualATradLoginSessionResource {
  session: ManualATradLoginSessionLike;
  close(): Promise<void>;
}

export interface ManualATradLoginRuntime {
  launchSession(config: ManualATradLoginConfig): Promise<ManualATradLoginSessionResource>;
  waitForUser(): Promise<void>;
  log(message: string): void;
}

export function createManualATradLoginConfig(args: string[] = []): ManualATradLoginConfig {
  return {
    baseUrl: parseBaseUrl(args),
    storageStatePath: ATRAD_STORAGE_STATE_PATH,
    persistentProfilePath: ATRAD_PERSISTENT_PROFILE_PATH,
    persistentProfile: args.includes('--persistent-profile'),
    headless: false,
    readonlyMode: true
  };
}

export function isSafeStorageStatePath(path: string): boolean {
  const normalized = path.replace(/\\/g, '/');
  return normalized === ATRAD_STORAGE_STATE_PATH;
}

export function isSafePersistentProfilePath(path: string): boolean {
  const normalized = path.replace(/\\/g, '/');
  return normalized === ATRAD_PERSISTENT_PROFILE_PATH;
}

export function formatManualATradLoginInstructions(config: ManualATradLoginConfig): string[] {
  return [
    'Sentinel-CSE manual ATrad session capture',
    `Opening: ${config.baseUrl}`,
    '',
    'Log in manually, complete 2FA if needed, then return to this terminal and press Enter.',
    'No credentials are read by this script, and no form fields are automated.',
    ...(config.persistentProfile
      ? [`Persistent profile will be saved at: ${config.persistentProfilePath}`]
      : []),
    `Storage state will be saved to: ${config.storageStatePath}`
  ];
}

export async function runManualATradLogin(
  config: ManualATradLoginConfig = createManualATradLoginConfig(),
  runtime: ManualATradLoginRuntime = defaultRuntime()
): Promise<string> {
  if (config.readonlyMode !== true || config.headless !== false) {
    throw new Error('Manual ATrad login must run visibly with readonlyMode: true.');
  }

  if (!isSafeStorageStatePath(config.storageStatePath)) {
    throw new Error(`Unsafe storage state path: ${config.storageStatePath}`);
  }

  if (!isSafePersistentProfilePath(config.persistentProfilePath)) {
    throw new Error(`Unsafe persistent profile path: ${config.persistentProfilePath}`);
  }

  assertATradReadOnlySafety('manual read-only session storage capture');

  await mkdir(dirname(config.storageStatePath), { recursive: true });
  if (config.persistentProfile) {
    await mkdir(config.persistentProfilePath, { recursive: true });
  }

  const resource = await runtime.launchSession(config);

  try {
    const page = resource.session.pages()[0] ?? (await resource.session.newPage());
    await page.goto(config.baseUrl, { waitUntil: 'domcontentloaded' });

    for (const line of formatManualATradLoginInstructions(config)) {
      runtime.log(line);
    }

    await runtime.waitForUser();
    await saveStorageState(resource.session, config.storageStatePath);

    const message = config.persistentProfile
      ? `ATrad persistent profile ready at ${config.persistentProfilePath}. Storage state also saved to ${config.storageStatePath}`
      : `ATrad storage state saved to ${config.storageStatePath}`;
    runtime.log(message);
    return config.persistentProfile ? config.persistentProfilePath : config.storageStatePath;
  } finally {
    await resource.close();
  }
}

function parseBaseUrl(args: string[]): string {
  const flagIndex = args.findIndex((arg) => arg === '--base-url');
  const candidate = flagIndex >= 0 ? args[flagIndex + 1] : args.find((arg) => !arg.startsWith('--'));
  const baseUrl = candidate?.trim() || DEFAULT_ATRAD_BASE_URL;

  try {
    return new URL(baseUrl).toString();
  } catch {
    throw new Error(`Invalid ATrad base URL: ${baseUrl}`);
  }
}

function defaultRuntime(): ManualATradLoginRuntime {
  return {
    launchSession: async (config) => {
      if (config.persistentProfile) {
        const context = await chromium.launchPersistentContext(config.persistentProfilePath, {
          headless: config.headless
        });
        return {
          session: context,
          close: async () => context.close()
        };
      }

      const browser = await chromium.launch({ headless: config.headless });
      const context = await browser.newContext();
      return {
        session: context,
        close: async () => browser.close()
      };
    },
    waitForUser: async () => {
      const readline = createInterface({ input, output });
      try {
        await readline.question('');
      } finally {
        readline.close();
      }
    },
    log: (message) => console.log(message)
  };
}

async function saveStorageState(context: BrowserContext | ManualATradLoginSessionLike, path: string): Promise<void> {
  assertATradReadOnlySafety('save read-only browser storage state');
  await context.storageState({ path });
}

async function main(): Promise<void> {
  await runManualATradLogin(createManualATradLoginConfig(process.argv.slice(2)));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual ATrad login failed: ${message}`);
    process.exitCode = 1;
  });
}
