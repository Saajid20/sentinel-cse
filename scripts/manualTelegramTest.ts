import { RealTelegramAlertSender, TelegramAlertMessage } from '../packages/telegram/src/index.js';
import { pathToFileURL } from 'node:url';

const testMessageText = 'Sentinel-CSE Telegram test alert. Signal-only mode is active.';

export async function runManualTelegramTest(): Promise<void> {
  const botToken = requiredEnv('TELEGRAM_BOT_TOKEN');
  const chatId = requiredEnv('TELEGRAM_CHAT_ID');

  const sender = new RealTelegramAlertSender({
    botToken,
    chatId
  });

  const message: TelegramAlertMessage = {
    id: `manual-telegram-test-${Date.now()}`,
    kind: 'BUY_WATCH',
    text: testMessageText,
    createdAt: Date.now()
  };

  await sender.send(message);
}

async function main(): Promise<void> {
  await runManualTelegramTest();
  console.log('Sent one manual Telegram test message.');
}

export function requiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for the manual Telegram test`);
  }

  return value;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Manual Telegram test failed: ${message}`);
    process.exitCode = 1;
  });
}
