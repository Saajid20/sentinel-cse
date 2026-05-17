import { pathToFileURL } from 'node:url';
import {
  findInvalidUniverseTickerEntries,
  loadTradeableUniverseConfig
} from './tradeableUniverse.js';

export interface ValidateTradeableUniverseConfig {
  configPath: string;
}

export interface ValidateTradeableUniverseResult {
  ok: boolean;
  output: string;
}

export function createValidateTradeableUniverseConfig(args: string[] = []): ValidateTradeableUniverseConfig {
  const configPath = readFlagValue(args, '--config') ?? 'config/tradeableUniverse.example.json';
  return { configPath };
}

export async function runValidateTradeableUniverse(
  config: ValidateTradeableUniverseConfig = createValidateTradeableUniverseConfig()
): Promise<ValidateTradeableUniverseResult> {
  const universe = await loadTradeableUniverseConfig(config.configPath);
  const invalidTickers = findInvalidUniverseTickerEntries(universe);
  const lines = [
    'Sentinel-CSE tradeable universe validation',
    `config: ${config.configPath}`,
    `name: ${universe.name}`,
    `includeTickers: ${universe.includeTickers.length}`,
    `excludeTickers: ${universe.excludeTickers.length}`,
    `excludePatterns: ${universe.excludePatterns.length}`,
    `invalid ticker entries: ${invalidTickers.length}`
  ];

  invalidTickers.slice(0, 10).forEach((ticker) => {
    lines.push(`- invalid ticker: ${ticker}`);
  });

  return {
    ok: invalidTickers.length === 0,
    output: lines.join('\n')
  };
}

function readFlagValue(args: string[], flag: string): string | undefined {
  const index = args.findIndex((arg) => arg === flag);
  return index >= 0 ? args[index + 1] : undefined;
}

async function main(): Promise<void> {
  const result = await runValidateTradeableUniverse(
    createValidateTradeableUniverseConfig(process.argv.slice(2))
  );
  console.log(result.output);
  process.exitCode = result.ok ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Tradeable universe validation failed: ${message}`);
    process.exitCode = 1;
  });
}
