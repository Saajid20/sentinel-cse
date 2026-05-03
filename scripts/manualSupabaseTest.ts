import {
  DbMarketSnapshot,
  SupabaseLikeClient,
  SupabaseLikeQuery,
  SupabaseLikeTable,
  SupabaseMarketSnapshotRepository,
  SupabaseResult,
  SupabaseRow
} from '../packages/db/src/index.js';
import { pathToFileURL } from 'node:url';

export async function runManualSupabaseTest(): Promise<string> {
  const supabaseUrl = requiredEnv('SUPABASE_URL');
  const supabaseKey = optionalEnv('SUPABASE_SERVICE_ROLE_KEY') ?? optionalEnv('SUPABASE_ANON_KEY');

  if (!supabaseKey) {
    throw new Error('SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY is required for the manual Supabase test');
  }

  const client = createSupabaseRestClient({
    supabaseUrl,
    supabaseKey
  });
  const repository = new SupabaseMarketSnapshotRepository(client);
  const now = Date.now();
  const snapshot: DbMarketSnapshot = {
    id: `manual-supabase-test-${now}`,
    ticker: 'MANUAL.TEST',
    snapshotTime: now,
    lastPrice: 1,
    bestBid: 0.99,
    bestAsk: 1.01,
    bidDepth: 100,
    askDepth: 100,
    volume: 1,
    totalTurnover: 1,
    metadata: {
      source: 'manual-supabase-test'
    },
    createdAt: now
  };

  await repository.save(snapshot);

  const snapshots = await repository.listByTicker(snapshot.ticker);
  const inserted = snapshots.find((candidate) => candidate.id === snapshot.id);
  if (!inserted) {
    throw new Error(`Inserted market snapshot ${snapshot.id} was not found`);
  }

  return snapshot.id;
}

async function main(): Promise<void> {
  const snapshotId = await runManualSupabaseTest();
  console.log(`Supabase manual test succeeded: inserted and read market_snapshots row ${snapshotId}`);
}

interface SupabaseRestConfig {
  supabaseUrl: string;
  supabaseKey: string;
}

function createSupabaseRestClient(config: SupabaseRestConfig): SupabaseLikeClient {
  const baseUrl = config.supabaseUrl.replace(/\/+$/, '');

  return {
    from<T = SupabaseRow>(tableName: string): SupabaseLikeTable<T> {
      return {
        insert: async (values) => {
          const response = await fetch(`${baseUrl}/rest/v1/${tableName}`, {
            method: 'POST',
            headers: headers(config.supabaseKey, {
              Prefer: 'return=representation'
            }),
            body: JSON.stringify(toSupabaseRows(values))
          });

          return responseToResult<T>(response);
        },
        update: (values) => new SupabaseRestQuery<T>(baseUrl, config.supabaseKey, tableName, 'PATCH', values),
        select: () => new SupabaseRestQuery<T>(baseUrl, config.supabaseKey, tableName, 'GET')
      };
    }
  };
}

class SupabaseRestQuery<T = SupabaseRow> implements SupabaseLikeQuery<T> {
  private readonly filters: Array<{ column: string; value: unknown }> = [];

  constructor(
    private readonly baseUrl: string,
    private readonly supabaseKey: string,
    private readonly tableName: string,
    private readonly method: 'GET' | 'PATCH',
    private readonly values?: Partial<T>
  ) {}

  eq(column: string, value: unknown): SupabaseLikeQuery<T> {
    this.filters.push({ column, value });
    return this;
  }

  async execute(): Promise<SupabaseResult<T>> {
    const url = new URL(`${this.baseUrl}/rest/v1/${this.tableName}`);
    url.searchParams.set('select', '*');
    for (const filter of this.filters) {
      url.searchParams.set(filter.column, `eq.${String(filter.value)}`);
    }

    const response = await fetch(url, {
      method: this.method,
      headers: headers(this.supabaseKey, this.method === 'PATCH' ? { Prefer: 'return=representation' } : undefined),
      body: this.method === 'PATCH' ? JSON.stringify(this.values) : undefined
    });

    return responseToResult<T>(response);
  }

  async maybeSingle(): Promise<SupabaseResult<T>> {
    const result = await this.execute();
    const data = Array.isArray(result.data) ? result.data[0] ?? null : result.data;

    return {
      data,
      error: result.error
    };
  }
}

function toSupabaseRows<T>(values: T | T[]): SupabaseRow | SupabaseRow[] {
  if (Array.isArray(values)) {
    return values.map(toSupabaseRow);
  }

  return toSupabaseRow(values);
}

function toSupabaseRow<T>(value: T): SupabaseRow {
  return normalizeOutgoingRow(JSON.parse(JSON.stringify(value)) as SupabaseRow);
}

function headers(supabaseKey: string, extra: Record<string, string> = {}): Record<string, string> {
  return {
    apikey: supabaseKey,
    Authorization: `Bearer ${supabaseKey}`,
    'content-type': 'application/json',
    ...extra
  };
}

async function responseToResult<T>(response: Response): Promise<SupabaseResult<T>> {
  const text = await response.text();
  const parsed = text ? (JSON.parse(text) as SupabaseRow[] | SupabaseRow) : null;
  const data = parsed ? normalizeIncomingRows(parsed) : null;

  if (!response.ok) {
    return {
      data: null,
      error: {
        message: text || `Supabase request failed with status ${response.status}`
      }
    };
  }

  return {
    data,
    error: null
  };
}

function normalizeOutgoingRow(row: SupabaseRow): SupabaseRow {
  const timestampColumns = new Set([
    'snapshot_time',
    'created_at',
    'candle_time',
    'valid_until',
    'updated_at',
    'event_time',
    'opened_at',
    'closed_at'
  ]);
  const normalized: SupabaseRow = { ...row };

  for (const column of timestampColumns) {
    const value = normalized[column];
    if (typeof value === 'number') {
      normalized[column] = new Date(value).toISOString();
    }
  }

  return normalized;
}

function normalizeIncomingRows<T>(rows: SupabaseRow[] | SupabaseRow): T[] | T {
  if (Array.isArray(rows)) {
    return rows.map(normalizeIncomingRow) as T[];
  }

  return normalizeIncomingRow(rows) as T;
}

function normalizeIncomingRow(row: SupabaseRow): SupabaseRow {
  const timestampColumns = new Set([
    'snapshot_time',
    'created_at',
    'candle_time',
    'valid_until',
    'updated_at',
    'event_time',
    'opened_at',
    'closed_at'
  ]);
  const normalized: SupabaseRow = { ...row };

  for (const column of timestampColumns) {
    const value = normalized[column];
    if (typeof value === 'string') {
      const timestamp = Date.parse(value);
      normalized[column] = Number.isFinite(timestamp) ? timestamp : value;
    }
  }

  return normalized;
}

export function requiredEnv(name: string): string {
  const value = optionalEnv(name);
  if (!value) {
    throw new Error(`${name} is required for the manual Supabase test`);
  }

  return value;
}

export function optionalEnv(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual Supabase test failed: ${message}`);
    process.exitCode = 1;
  });
}
