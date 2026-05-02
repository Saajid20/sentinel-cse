import { MemoryAgent, Signal, SignalEvent, SignalOutcome } from './types.js';

export class InMemorySignalMemory implements MemoryAgent {
  private signals = new Map<string, Signal>();
  private events: SignalEvent[] = [];
  private outcomes = new Map<string, SignalOutcome>();

  async saveSignal(signal: Signal): Promise<void> {
    this.signals.set(signal.id, this.cloneSignal(signal));
  }

  async recordEvent(event: SignalEvent): Promise<void> {
    this.events.push(this.cloneEvent(event));
  }

  async updateSignal(signal: Signal): Promise<void> {
    this.signals.set(signal.id, this.cloneSignal(signal));
  }

  async closeSignalOutcome(outcome: SignalOutcome): Promise<void> {
    this.outcomes.set(outcome.signalId, this.cloneOutcome(outcome));
  }

  async getSignal(signalId: string): Promise<Signal | null> {
    const signal = this.signals.get(signalId);
    return signal ? this.cloneSignal(signal) : null;
  }

  async listSignalsByTicker(ticker: string): Promise<Signal[]> {
    return Array.from(this.signals.values())
      .filter((signal) => signal.ticker === ticker)
      .map((signal) => this.cloneSignal(signal));
  }

  async listActiveSignals(): Promise<Signal[]> {
    return Array.from(this.signals.values())
      .filter((signal) => signal.status === 'ACTIVE')
      .map((signal) => this.cloneSignal(signal));
  }

  async getOutcomesByStrategy(strategy: string): Promise<SignalOutcome[]> {
    return Array.from(this.outcomes.values())
      .filter((outcome) => this.signals.get(outcome.signalId)?.strategy === strategy)
      .map((outcome) => this.cloneOutcome(outcome));
  }

  async listEventsBySignal(signalId: string): Promise<SignalEvent[]> {
    return this.events
      .filter((event) => event.signalId === signalId)
      .map((event) => this.cloneEvent(event));
  }

  private cloneSignal(signal: Signal): Signal {
    return {
      ...signal,
      entryZone: [...signal.entryZone],
      targets: [...signal.targets],
      features: { ...signal.features }
    };
  }

  private cloneEvent(event: SignalEvent): SignalEvent {
    return { ...event };
  }

  private cloneOutcome(outcome: SignalOutcome): SignalOutcome {
    return { ...outcome };
  }
}
