import type { Clock } from './types.ts';

export interface Page<T> {
  readonly items: readonly T[];
  readonly nextCursor: string | null;
}

export interface Checkpoint {
  readonly cursor: string | null;
  readonly done: boolean;
}

export interface ExtractOptions<T> {
  readonly fetchPage: (cursor: string | null) => Promise<Page<T>>;
  readonly upsert: (items: readonly T[]) => Promise<void>;
  readonly saveCheckpoint: (checkpoint: Checkpoint) => Promise<void>;
  readonly cursor: string | null;
  readonly budgetMs: number;
  readonly clock: Clock;
}

export interface ExtractResult {
  readonly status: 'complete' | 'budget_exhausted';
  readonly checkpoint: Checkpoint;
  readonly pages: number;
}

export async function extract<T>(o: ExtractOptions<T>): Promise<ExtractResult> {
  const startedAt = o.clock();
  let cursor = o.cursor;
  let pages = 0;
  let slowestPageMs = 0;

  for (;;) {
    const remainingMs = o.budgetMs - (o.clock() - startedAt);
    if (remainingMs <= 0 || remainingMs < slowestPageMs) {
      return { status: 'budget_exhausted', checkpoint: { cursor, done: false }, pages };
    }

    const pageStartedAt = o.clock();
    const page = await o.fetchPage(cursor);
    await o.upsert(page.items);
    const checkpoint: Checkpoint = { cursor: page.nextCursor, done: page.nextCursor === null };
    await o.saveCheckpoint(checkpoint);

    pages++;
    if (checkpoint.done) return { status: 'complete', checkpoint, pages };
    cursor = page.nextCursor;
    slowestPageMs = Math.max(slowestPageMs, o.clock() - pageStartedAt);
  }
}
