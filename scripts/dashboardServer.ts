import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  createSentinelDashboardConfig,
  runSentinelDashboard,
  type SentinelDashboardConfig,
  type SentinelDashboardRuntime,
  type SentinelDashboardSummary
} from './sentinelDashboard.js';

export interface DashboardServerConfig extends SentinelDashboardConfig {
  port: number;
  host: string;
  staticDir: string;
}

export interface DashboardCommandSnippet {
  label: string;
  command: string;
}

export interface DashboardApiResponse extends SentinelDashboardSummary {
  commandSnippets: DashboardCommandSnippet[];
}

export interface DashboardServerHandle {
  server: Server;
  url: string;
}

const DEFAULT_DASHBOARD_PORT = 8787;
const DEFAULT_DASHBOARD_HOST = '127.0.0.1';
const DEFAULT_STATIC_DIR = 'web/dashboard';

export function createDashboardServerConfig(args: string[] = []): DashboardServerConfig {
  return {
    ...createSentinelDashboardConfig(args),
    port: readIntegerFlag(args, '--port', DEFAULT_DASHBOARD_PORT),
    host: readFlagValue(args, '--host') ?? DEFAULT_DASHBOARD_HOST,
    staticDir: readFlagValue(args, '--static-dir') ?? DEFAULT_STATIC_DIR
  };
}

export async function buildDashboardApiResponse(
  config: DashboardServerConfig = createDashboardServerConfig(),
  runtime?: SentinelDashboardRuntime
): Promise<DashboardApiResponse> {
  const summary = await runSentinelDashboard(config, runtime);
  return {
    ...summary,
    commandSnippets: buildDashboardCommandSnippets(summary)
  };
}

export function buildDashboardCommandSnippets(
  summary: SentinelDashboardSummary
): DashboardCommandSnippet[] {
  const latestSession = summary.localFiles.latestSessionFilePath ?? '<latest-session>';
  return [
    {
      label: 'Record an open-market session',
      command: 'pnpm atrad:record-session -- --base-url "https://online.fge.lk/atsweb/login" --duration-seconds 600 --interval-seconds 10 --max-ticks 60'
    },
    {
      label: 'Replay latest session with universe',
      command: `pnpm atrad:replay-session -- --input "${latestSession}" --universe "config/tradeableUniverse.json"`
    },
    {
      label: 'Validate local universe config',
      command: 'pnpm universe:validate -- --config config/tradeableUniverse.json'
    },
    {
      label: 'Print terminal dashboard',
      command: 'pnpm sentinel dashboard'
    }
  ];
}

export function createDashboardServer(
  config: DashboardServerConfig = createDashboardServerConfig(),
  runtime?: SentinelDashboardRuntime
): Server {
  return createServer(async (request, response) => {
    try {
      await handleDashboardRequest(request, response, config, runtime);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      sendJson(response, 500, { error: `Dashboard request failed: ${message}` });
    }
  });
}

export async function startDashboardServer(
  config: DashboardServerConfig = createDashboardServerConfig()
): Promise<DashboardServerHandle> {
  const server = createDashboardServer(config);
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(config.port, config.host, () => {
      server.off('error', reject);
      resolve();
    });
  });

  const address = server.address();
  const port = typeof address === 'object' && address ? address.port : config.port;
  return {
    server,
    url: `http://${config.host}:${port}`
  };
}

async function handleDashboardRequest(
  request: IncomingMessage,
  response: ServerResponse,
  config: DashboardServerConfig,
  runtime?: SentinelDashboardRuntime
): Promise<void> {
  const url = new URL(request.url ?? '/', `http://${request.headers.host ?? 'localhost'}`);

  if (request.method !== 'GET') {
    sendText(response, 405, 'Method not allowed', 'text/plain; charset=utf-8');
    return;
  }

  if (url.pathname === '/api/dashboard') {
    sendJson(response, 200, await buildDashboardApiResponse(config, runtime));
    return;
  }

  const assetPath = url.pathname === '/' ? '/index.html' : url.pathname;
  await serveStaticAsset(response, config.staticDir, assetPath);
}

async function serveStaticAsset(
  response: ServerResponse,
  staticDir: string,
  assetPath: string
): Promise<void> {
  const normalizedPath = normalize(assetPath).replace(/^(\.\.[/\\])+/, '');
  const relativePath = normalizedPath.replace(/^[/\\]+/, '');
  const fullPath = join(staticDir, relativePath);

  try {
    const contents = await readFile(fullPath);
    sendBuffer(response, 200, contents, contentTypeForPath(fullPath));
  } catch {
    sendText(response, 404, 'Not found', 'text/plain; charset=utf-8');
  }
}

function sendJson(response: ServerResponse, statusCode: number, body: unknown): void {
  sendText(response, statusCode, JSON.stringify(body, null, 2), 'application/json; charset=utf-8');
}

function sendText(
  response: ServerResponse,
  statusCode: number,
  body: string,
  contentType: string
): void {
  response.writeHead(statusCode, {
    'content-type': contentType,
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff'
  });
  response.end(body);
}

function sendBuffer(
  response: ServerResponse,
  statusCode: number,
  body: Buffer,
  contentType: string
): void {
  response.writeHead(statusCode, {
    'content-type': contentType,
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff'
  });
  response.end(body);
}

function contentTypeForPath(path: string): string {
  switch (extname(path)) {
    case '.html':
      return 'text/html; charset=utf-8';
    case '.js':
      return 'text/javascript; charset=utf-8';
    case '.css':
      return 'text/css; charset=utf-8';
    default:
      return 'application/octet-stream';
  }
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

function readIntegerFlag(args: string[], flag: string, fallback: number): number {
  const value = readFlagValue(args, flag);
  if (value === undefined) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`Invalid ${flag} value: ${value}`);
  }
  return parsed;
}

async function main(): Promise<void> {
  const config = createDashboardServerConfig(process.argv.slice(2));
  const handle = await startDashboardServer(config);
  console.log(`Sentinel-CSE read-only dashboard: ${handle.url}`);
  console.log('Safety reminder: local files only; no live ATrad, Telegram, Supabase, orders, or auto-trading.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Dashboard server failed: ${message}`);
    process.exitCode = 1;
  });
}
