# Build an accurate countdown or stopwatch that survives background tabs
**Round:** 06 · Machine Coding · **Level:** Senior · **Time:** 20 min · **Tags:** timers · setinterval · drift
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
A naive `setInterval` countdown drifts by minutes under background tabs, sleep or a busy main thread. Build one that stays accurate, with start/pause/resume/reset, stops at zero, fires `onComplete` once, and cleans up.

Tests (fake timers + controllable clock): 10 s countdown after 3 s shows 7 s even if only one tick happened; pause at 4 s, wait 5 s, resume → still 4 s; jump clock +30 s (sleep) → 00:00 and `onComplete` once; unmount leaves no timers/listeners.

## Core answer (key points)
- **Never count ticks.** Store a deadline (countdown) or start + accumulated (stopwatch) and *compute* remaining/elapsed from a clock each render. Ticks only request a re-render.
- **Monotonic clock:** `performance.now()` doesn't jump with system clock changes; `Date.now()` does (NTP, manual change).
- **Why ticks lie:** timers are clamped/throttled in background tabs (≥1 s, more under intensive throttling), delayed by long tasks, and paused during sleep. Deadline math makes lateness affect only *when* the display updates, never the value.
- **Align ticks** to the next whole-second boundary (`remaining % 1000`) so the display never skips or repeats a second.
- **Re-sync on `visibilitychange`** → immediate tick when the tab returns.
- **Pause/resume:** pause stores `remaining`; resume sets `deadline = now + remaining`.
- **Completion:** when remaining hits 0, stop scheduling and fire `onComplete` once (ref guard).
- **A11y:** visual digits `aria-hidden`; announce via polite live region only at meaningful moments (minute marks, "Time is up"), never every second. `font-variant-numeric: tabular-nums` to avoid jitter.
- **Server-authoritative deadlines** (auctions, seat holds): estimate client/server offset NTP-style from request midpoint; server still decides.
- **Stopwatch:** `elapsed = accumulated + (running ? now - startedAt : 0)`; centiseconds via `requestAnimationFrame` only while visible.

## Mental model / flow
```
state: { status: idle|running|paused|done, deadline, remainingAtPause }
render: remaining = status==running ? max(0, deadline - now()) : remainingAtPause
tick scheduler (only while running):
  setTimeout(tick, remaining % 1000 + small epsilon)
  tick → setNow(now()) → remaining<=0 ? done + onComplete once : reschedule
visibilitychange(visible) → clear + tick now
```

## Code sketch
```ts
type Clock = () => number;

export function useCountdown(totalMs: number, { onComplete, clock = () => performance.now() }:
  { onComplete?: () => void; clock?: Clock } = {}) {
  const [s, setS] = useState({ status: 'idle' as 'idle' | 'running' | 'paused' | 'done',
                               deadline: 0, left: totalMs });
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const fired = useRef(false);
  const done = useRef(onComplete);
  useLayoutEffect(() => { done.current = onComplete; });

  const remaining = s.status === 'running' ? Math.max(0, s.deadline - clock()) : s.left;

  useEffect(() => {
    if (s.status !== 'running') return;
    let t: ReturnType<typeof setTimeout>;
    const tick = () => {
      const left = s.deadline - clock();
      if (left <= 0) {
        setS({ status: 'done', deadline: s.deadline, left: 0 });
        if (!fired.current) { fired.current = true; done.current?.(); }
        return;
      }
      rerender();
      t = setTimeout(tick, (left % 1000) + 4);
    };
    tick();
    const onVis = () => { if (document.visibilityState === 'visible') { clearTimeout(t); tick(); } };
    document.addEventListener('visibilitychange', onVis);
    return () => { clearTimeout(t); document.removeEventListener('visibilitychange', onVis); };
  }, [s.status, s.deadline, clock]);

  return {
    remaining, status: s.status,
    start:  () => { fired.current = false; setS({ status: 'running', deadline: clock() + totalMs, left: totalMs }); },
    pause:  () => setS(p => p.status === 'running' ? { ...p, status: 'paused', left: Math.max(0, p.deadline - clock()) } : p),
    resume: () => setS(p => p.status === 'paused' ? { ...p, status: 'running', deadline: clock() + p.left } : p),
    reset:  () => { fired.current = false; setS({ status: 'idle', deadline: 0, left: totalMs }); },
  };
}

const fmt = (ms: number) => {
  const sec = Math.ceil(ms / 1000);
  return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`;
};
```
```ts
// Server offset (NTP-style midpoint)
const t0 = Date.now();
const { serverNow, expiresAt } = await getHold();
const t1 = Date.now();
const skew = serverNow - (t0 + t1) / 2;
const localExpiry = expiresAt - skew; // compare to Date.now() — epoch domain, not performance.now()
```
Injecting `clock` makes the tests deterministic: advance a fake clock by 30 s, fire one timer, assert `00:00` and one `onComplete`.

## Trade-offs & pitfalls
- `Math.ceil` for countdown display (shows 1 until truly 0), `Math.floor` for stopwatch.
- `performance.now()` is relative to page load and can't be persisted; for survive-reload, persist an epoch deadline with `Date.now()` and accept its jumps.
- Whether `performance.now()` advances during system sleep differs by browser/OS — I'm not certain of current behavior everywhere; the visibility re-sync plus deadline math handles either.
- rAF stops in background tabs; never use it as the source of truth.
- Web Workers timers are also throttled in some browsers; not a fix for accuracy, only for main-thread contention.

## Likely follow-ups
- **Why not `setInterval(1000)`?** Drifts (each callback late by a few ms accumulates), throttled when hidden, misaligned with paint.
- **Need sub-second accuracy for an action at zero?** Do the action server-side or schedule on deadline, not on display tick.
- **Many timers on one page?** One shared ticker (single timeout/rAF) broadcasting to subscribers via `useSyncExternalStore`.
- **Reduced motion?** No animated ring updates; text only.

## Say it in 60 seconds
I never count ticks. I store a deadline and compute remaining time from `performance.now()` on every render, so a late, throttled or paused timer only delays the display, never corrupts the value. Ticks are scheduled to the next whole-second boundary so seconds never skip or repeat, and on `visibilitychange` I tick immediately to catch up. Pause stores the remaining time, resume makes a new deadline from it. At zero I stop scheduling and fire `onComplete` once behind a ref guard, and the effect cleanup clears the timeout and listener. The clock is injectable for tests. For screen readers I announce only meaningful moments, and for server-owned deadlines I correct for clock skew while the server stays authoritative.
