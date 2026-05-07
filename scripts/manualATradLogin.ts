import { mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { pathToFileURL } from 'node:url';
import { stdin as input, stdout as output } from 'node:process';
import { chromium, type Browser, type BrowserContext } from 'playwright';
import { assertATradReadOnlySafety } from '../packages/atrad/src/index.js';

export const DEFAULT_ATRAD_BASE_URL = 'https://example.invalid/atrad-login';
export const ATRAD_STORAGE_STATE_PATH = 'playwright/.auth/atrad-storage-state.json';

export interface ManualATradLoginConfig {
  baseUrl: string;
  storageStatePath: string;
  headless: false;
  readonlyMode: true;
}

export interface ManualATradLoginRuntime {
  launchBrowser(config: ManualATradLoginConfig): Promise<Browser>;
  waitForUser(): Promise<void>;
  log(message: string): void;
}

export function createManualATradLoginConfig(args: string[] = []): ManualATradLoginConfig {
  return {
    baseUrl: parseBaseUrl(args),
    storageStatePath: ATRAD_STORAGE_STATE_PATH,
    headless: false,
    readonlyMode: true
  };
}

export function isSafeStorageStatePath(path: string): boolean {
  const normalized = path.replace(/\\/g, '/');
  return normalized === ATRAD_STORAGE_STATE_PATH;
}

export function formatManualATradLoginInstructions(config: ManualATradLoginConfig): string[] {
  return [
    'Sentinel-CSE manual ATrad session capture',
    `Opening: ${config.baseUrl}`,
    '',
    'Log in manually, complete 2FA if needed, then return to this terminal and press Enter.',
    'No credentials are read by this script, and no form fields are automated.',
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

  assertATradReadOnlySafety('manual read-only session storage capture');

  await mkdir(dirname(config.storageStatePath), { recursive: true });
  const browser = await runtime.launchBrowser(config);

  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(config.baseUrl, { waitUntil: 'domcontentloaded' });

    for (const line of formatManualATradLoginInstructions(config)) {
      runtime.log(line);
    }

    await runtime.waitForUser();
    await saveStorageState(context, config.storageStatePath);

    const message = `ATrad storage state saved to ${config.storageStatePath}`;
    runtime.log(message);
    return config.storageStatePath;
  } finally {
    await browser.close();
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
    launchBrowser: async (config) => chromium.launch({ headless: config.headless }),
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

async function saveStorageState(context: BrowserContext, path: string): Promise<void> {
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
