# Build progress bars that each fill in n seconds and run one after another when you click quickly
**Round:** 06 · Machine Coding · **Level:** Senior · **Time:** 30 min · **Tags:** machine coding · progress bar · queue
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
Each click adds a bar that fills 0 → 100% in n seconds; bars run strictly one at a time in click order. Timing and queueing must be reusable and separate from UI; accessible progress semantics; no leaked timers.

Tests: three clicks with n=3 → finish at 3 s, 6 s, 9 s; bars 2 and 3 show "Waiting" meanwhile; a click after all finished starts immediately; removing a waiting bar skips it without stalling; unmount mid-run stops animation; a tab hidden for 10 s resumes at the right place.

## Core answer (key points)
- **Clarify first:** on click during a run — queue (this one), ignore, restart, or parallel? Cancel allowed? Fake timer bar vs real work progress? The answer changes the data structure.
- **Two framework-free pieces:**
  1. **`animate(durationMs, onProgress, signal)`** → Promise. Progress = `(now - start) / duration` from `performance.now()` per rAF frame. Time-derived, so throttled/hidden tabs catch up instead of lagging. Rejects with `AbortError` on abort and cancels the frame.
  2. **Serial queue** via a promise tail: `tail = tail.then(task)`; swallow the settled result in the tail so one failure/cancel doesn't block everything after.
- **UI:** each bar owns its own `{ status, ratio }`, so a frame re-renders one bar. On mount it enqueues "animate me"; cleanup aborts (also handles Strict Mode double mount and removal while waiting — the task checks `signal.aborted` first and exits).
- **Queue instance per component** (`useState(createSerialQueue)`), never module-global (two instances/tests would share it).
- **Rendering:** `transform: scaleX(ratio)` (compositor) rather than `width` (layout each frame). Optionally write ratio to a CSS variable via ref and keep React state to status only.
- **A11y:** `role="progressbar"` with `aria-valuemin/max/now`, `aria-label`, visible text "Waiting / 42% / Done".

## Mental model / flow
```
click → ids.push(n) → <Bar n> mounts → enqueue(task_n)
tail: P0 ──then(task1)──► P1 ──then(task2)──► P2 ──then(task3)
task_k: if aborted → throw AbortError (skip)
        status=running; await animate(n*1000, setRatio, signal); status=done
unmount/remove → controller.abort() → rAF cancelled / task skipped → tail continues
```

## Code sketch
```ts
export function animate(ms: number, onProgress: (r: number) => void, signal?: AbortSignal,
                        raf = requestAnimationFrame, caf = cancelAnimationFrame, now = () => performance.now()) {
  return new Promise<void>((resolve, reject) => {
    const abortErr = () => new DOMException('aborted', 'AbortError');
    if (signal?.aborted) return reject(abortErr());
    const t0 = now();
    let id = 0;
    const frame = () => {
      const r = ms <= 0 ? 1 : Math.min(1, (now() - t0) / ms);
      onProgress(r);
      if (r < 1) id = raf(frame); else resolve();
    };
    id = raf(frame);
    signal?.addEventListener('abort', () => { caf(id); reject(abortErr()); }, { once: true });
  });
}

export function createSerialQueue() {
  let tail: Promise<unknown> = Promise.resolve();
  return <T>(task: () => Promise<T>): Promise<T> => {
    const run = tail.then(task);
    tail = run.catch(() => undefined);     // keep the chain alive after failures
    return run;
  };
}
export type Enqueue = ReturnType<typeof createSerialQueue>;
const isAbort = (e: unknown) => e instanceof DOMException && e.name === 'AbortError';
```
```tsx
function Bar({ seconds, enqueue, label }: { seconds: number; enqueue: Enqueue; label: string }) {
  const [s, setS] = useState<{ status: 'waiting' | 'running' | 'done'; r: number }>({ status: 'waiting', r: 0 });
  useEffect(() => {
    const ac = new AbortController();
    enqueue(async () => {
      if (ac.signal.aborted) throw new DOMException('aborted', 'AbortError');
      await animate(seconds * 1000, r => setS({ status: 'running', r }), ac.signal);
      setS({ status: 'done', r: 1 });
    }).catch(e => { if (!isAbort(e)) throw e; });
    return () => ac.abort();
  }, [seconds, enqueue]);

  const pct = Math.round(s.r * 100);
  return (
    <div className="row">
      <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} className="track">
        <div className="fill" style={{ transform: `scaleX(${s.r})`, transformOrigin: 'left' }} />
      </div>
      <span>{s.status === 'waiting' ? 'Waiting' : s.status === 'done' ? 'Done' : `${pct}%`}</span>
    </div>
  );
}

export function SequentialBars({ seconds = 3 }: { seconds?: number }) {
  const [enqueue] = useState(createSerialQueue);
  const [ids, setIds] = useState<number[]>([]);
  const seq = useRef(0);
  return (
    <>
      <button onClick={() => setIds(xs => [...xs, ++seq.current])}>Add bar ({seconds}s)</button>
      {ids.map(id => <Bar key={id} seconds={seconds} enqueue={enqueue} label={`Bar ${id}`} />)}
    </>
  );
}
```
Tests inject `raf`/`now` into `animate` so time advances deterministically; assert completion order 1, 2, 3 at 3/6/9 s and that a removed waiting bar never enters `running`.

## Trade-offs & pitfalls
- Strict Mode dev double mount enqueues twice; the first is aborted → skipped. Make sure skip happens *before* animating.
- `+= step per setInterval` drifts and stalls in background tabs — the classic wrong answer.
- A global `isRunning` flag + click counter breaks on removal and errors.
- `await` inside the click handler to chain bars blocks the handler and couples UI to the queue.
- Per-frame `setState` for many bars is fine for a handful; use the CSS-variable route for dozens.
- `n = 0`/NaN: guard at the boundary.

## Likely follow-ups
- **Run up to K at once?** Swap the serial queue for a concurrency pool (same as Q08's).
- **Pause/resume?** Track elapsed in the task, restart the frame loop from it; abort alone can't resume.
- **Cancel the running bar and continue?** Expose its controller; the queue treats abort like any settled task.
- **Why rAF not setInterval?** Paint-aligned, paused when hidden (and we recompute from the clock), no drift.

## Say it in 60 seconds
I'd first clarify that clicks during a run should queue. Then I build two framework-free pieces: an `animate` function that returns a promise and computes progress from elapsed time with requestAnimationFrame, so a hidden tab catches up instead of falling behind, and a serial queue that chains tasks on a promise tail and swallows each result so one failure or cancel doesn't block the rest. Each bar component owns its own progress state, enqueues itself on mount and aborts in cleanup, so removing a waiting bar just skips it and unmount stops the frame loop. The queue is created once per component, not globally. The bar uses `scaleX` for cheap animation and a proper `progressbar` role with value attributes, and I inject the clock and frame function to test timing deterministically.
