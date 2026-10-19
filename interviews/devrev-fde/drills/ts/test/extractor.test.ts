import { describe, expect, it } from 'vitest';
import { extract, type Checkpoint, type ExtractResult, type Page } from '../src/extractor.ts';
import { FakeClock } from './helpers.ts';

interface Item {
  readonly id: string;
  readonly value: number;
}

const TOTAL = 20;
const PAGE_SIZE = 3;
const PAGE_COUNT = Math.ceil(TOTAL / PAGE_SIZE);
const PAGE_COST_MS = 30;

type CrashPoint = 'after_fetch' | 'mid_upsert' | 'before_checkpoint';
class Crash extends Error {}

function world(crash?: { readonly point: CrashPoint; readonly page: number }) {
  const clock = new FakeClock();
  const source = Array.from({ length: TOTAL }, (_, i): Item => ({ id: `r${i}`, value: i * i }));
  const sink = new Map<string, Item>();
  const appended: Item[] = [];
  const fetchedCursors: (string | null)[] = [];
  let persisted: Checkpoint = { cursor: null, done: false };
  let pageIndex = -1;
  let armed = crash !== undefined;

  const maybeCrash = (point: CrashPoint) => {
    if (armed && crash!.point === point && crash!.page === pageIndex) {
      armed = false;
      throw new Crash(point);
    }
  };

  const fetchPage = async (cursor: string | null): Promise<Page<Item>> => {
    fetchedCursors.push(cursor);
    clock.advance(PAGE_COST_MS);
    const offset = cursor === null ? 0 : Number(cursor);
    pageIndex = offset / PAGE_SIZE;
    const next = offset + PAGE_SIZE;
    return { items: source.slice(offset, next), nextCursor: next >= TOTAL ? null : String(next) };
  };

  const upsert = async (items: readonly Item[]) => {
    maybeCrash('after_fetch');
    items.forEach((item, i) => {
      if (i === 1) maybeCrash('mid_upsert');
      sink.set(item.id, item);
      appended.push(item);
    });
  };

  const saveCheckpoint = async (checkpoint: Checkpoint) => {
    maybeCrash('before_checkpoint');
    persisted = checkpoint;
  };

  const invoke = (budgetMs: number): Promise<ExtractResult> =>
    extract({ fetchPage, upsert, saveCheckpoint, cursor: persisted.cursor, budgetMs, clock: clock.now });

  const runToCompletion = async (budgetMs: number) => {
    let invocations = 0;
    while (!persisted.done) {
      invocations++;
      await invoke(budgetMs);
      if (invocations > 100) throw new Error('no progress');
    }
    return invocations;
  };

  return {
    clock,
    sink,
    appended,
    fetchedCursors,
    invoke,
    runToCompletion,
    persisted: () => persisted,
  };
}

async function uninterruptedSink() {
  const w = world();
  await w.runToCompletion(1_000_000);
  return w.sink;
}

describe('extract: happy path', () => {
  it('walks every page, checkpointing after each, and reports completion', async () => {
    const saved: Checkpoint[] = [];
    const w = world();
    const result = await extract({
      fetchPage: async (cursor) => {
        const offset = cursor === null ? 0 : Number(cursor);
        return { items: [{ id: `r${offset}`, value: offset }], nextCursor: offset >= 2 ? null : String(offset + 1) };
      },
      upsert: async () => undefined,
      saveCheckpoint: async (cp) => {
        saved.push(cp);
      },
      cursor: null,
      budgetMs: 1000,
      clock: w.clock.now,
    });
    expect(result).toEqual({ status: 'complete', checkpoint: { cursor: null, done: true }, pages: 3 });
    expect(saved).toEqual([
      { cursor: '1', done: false },
      { cursor: '2', done: false },
      { cursor: null, done: true },
    ]);
  });

  it('upserts all rows in one invocation when the budget is ample', async () => {
    const w = world();
    const result = await w.invoke(10_000);
    expect(result.status).toBe('complete');
    expect(result.pages).toBe(PAGE_COUNT);
    expect(w.sink.size).toBe(TOTAL);
  });
});

describe('extract: time budget', () => {
  it('never calls fetchPage when no budget remains', async () => {
    const w = world();
    const result = await w.invoke(0);
    expect(result).toEqual({ status: 'budget_exhausted', checkpoint: { cursor: null, done: false }, pages: 0 });
    expect(w.fetchedCursors).toEqual([]);
  });

  it('stops before a page that would not fit, using the slowest page seen so far', async () => {
    const w = world();
    const result = await w.invoke(100);
    expect(result.pages).toBe(3);
    expect(result.checkpoint).toEqual({ cursor: '9', done: false });
    expect(w.clock.now()).toBe(90);
  });

  it('runs one more page exactly when the remaining time equals a page', async () => {
    const w = world();
    const result = await w.invoke(120);
    expect(result.pages).toBe(4);
    expect(w.clock.now()).toBe(120);
  });

  it('always makes progress with a positive budget smaller than one page', async () => {
    const w = world();
    const result = await w.invoke(1);
    expect(result.pages).toBe(1);
    expect(result.checkpoint).toEqual({ cursor: '3', done: false });
  });

  it('each new invocation resumes from the saved checkpoint without refetching', async () => {
    const w = world();
    await w.invoke(100);
    await w.invoke(100);
    await w.invoke(100);
    expect(w.fetchedCursors).toEqual([null, '3', '6', '9', '12', '15', '18']);
    expect(w.persisted()).toEqual({ cursor: null, done: true });
  });

  const budgets = [1, 29, 30, 31, 59, 60, 61, 89, 90, 119, 120, 121, 150, 209, 210, 211, 5000];

  it.each(budgets)('budget %ims: final data equals an uninterrupted run, and no invocation overruns', async (budget) => {
    const expected = await uninterruptedSink();
    const w = world();
    let overran = false;
    let invocations = 0;
    while (!w.persisted().done) {
      invocations++;
      const before = w.clock.now();
      await w.invoke(budget);
      if (budget >= PAGE_COST_MS && w.clock.now() - before > budget) overran = true;
    }
    expect(w.sink).toEqual(expected);
    expect(overran).toBe(false);
    expect(w.fetchedCursors).toHaveLength(PAGE_COUNT);
    const pagesPerInvocation = Math.max(1, Math.floor(budget / PAGE_COST_MS));
    expect(invocations).toBe(Math.ceil(PAGE_COUNT / pagesPerInvocation));
  });
});

describe('extract: crash between work and checkpoint', () => {
  const points: CrashPoint[] = ['after_fetch', 'mid_upsert', 'before_checkpoint'];
  const pages = Array.from({ length: PAGE_COUNT }, (_, i) => i);

  for (const point of points) {
    it.each(pages)(`${point} on page %i: replays exactly that one page and ends identical`, async (page) => {
      const expected = await uninterruptedSink();
      const w = world({ point, page });

      await expect(w.runToCompletion(10_000)).rejects.toBeInstanceOf(Crash);
      await w.runToCompletion(10_000);

      expect(w.sink).toEqual(expected);
      expect(w.fetchedCursors).toHaveLength(PAGE_COUNT + 1);
      const replayed = w.fetchedCursors.filter((c, i) => w.fetchedCursors.indexOf(c) !== i);
      expect(replayed).toEqual([w.fetchedCursors[page]]);
    });
  }

  it('would duplicate rows without an idempotent upsert: exactly one page of duplicates', async () => {
    const w = world({ point: 'before_checkpoint', page: 2 });
    await expect(w.runToCompletion(10_000)).rejects.toBeInstanceOf(Crash);
    await w.runToCompletion(10_000);
    expect(w.appended).toHaveLength(TOTAL + PAGE_SIZE);
    expect(w.sink.size).toBe(TOTAL);
  });

  it('loses at most one page of progress to a crash because the checkpoint trails by one page', async () => {
    const w = world({ point: 'before_checkpoint', page: 3 });
    await expect(w.runToCompletion(10_000)).rejects.toBeInstanceOf(Crash);
    expect(w.persisted()).toEqual({ cursor: '9', done: false });
  });
});
