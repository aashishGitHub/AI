import type { Json } from './types.ts';

export type EchoDecision = 'apply' | 'drop-as-echo' | 'conflict';

export function fingerprint(value: Json): string {
  if (Array.isArray(value)) return `[${value.map(fingerprint).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${fingerprint((value as { [k: string]: Json })[key]!)}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value);
}

export class EchoGuard {
  readonly #lastPushed = new Map<string, string>();

  recordPush(entityId: string, fp: string): void {
    this.#lastPushed.set(entityId, fp);
  }

  lastPushed(entityId: string): string | undefined {
    return this.#lastPushed.get(entityId);
  }

  decide(entityId: string, incoming: string, local: string | undefined): EchoDecision {
    const pushed = this.#lastPushed.get(entityId);
    if (incoming === pushed || incoming === local) return 'drop-as-echo';
    return local === pushed ? 'apply' : 'conflict';
  }
}
