# Walk through the event loop: tasks, microtasks, and where rendering fits
**Round:** 01 · JavaScript Internals · **Level:** Senior · **Time:** 15 min · **Tags:** event loop · microtasks · rendering
Source: https://whetstone-v1.vercel.app/#javascript-internals

## What they're really testing
Not print-order trivia. Can you explain *why* a UI freezes, why a spinner never paints, and why `setTimeout(fn, 0)` sometimes "fixes" it. Model first, puzzle second.

## Core answer (key points)
- One **task** runs at a time, to completion (click handler, timer callback, script, message event).
- When the call stack empties, the engine **drains every microtask**, including microtasks queued by microtasks (promise reactions, `queueMicrotask`, `MutationObserver`).
- Only then, if a frame is due (~16.7 ms at 60 Hz, but the browser decides), the **render step** runs: rAF callbacks → style → layout → (ResizeObserver / IntersectionObserver) → paint.
- So rendering happens **only between tasks**. A long task or an unbounded microtask chain blocks both paint and input.
- There are several task queues (input, timers, network). Browsers may prioritise input, so cross-queue ordering is not a contract.
- Spinner bug: `setLoading(true); heavySync(); setLoading(false)` all runs inside one task, so the frame showing `loading === true` never exists.
- Fixes, best first: move work to a Web Worker → chunk it and yield at a **task boundary** → at minimum defer the heavy part so one frame can paint (rAF then `setTimeout`).

## Mental model / flow
```
loop:
  1. pick ONE task from some task queue
  2. run it until the stack is empty
  3. drain ALL microtasks (re-check until empty)
  4. frame due?  -> rAF callbacks -> style -> layout -> observers -> paint
  5. idle?       -> requestIdleCallback
```
Puzzle in one handler: sync logs, `setTimeout`, `Promise.then`, `queueMicrotask`, rAF, and an async fn with `await`.
- Sync first (including the sync part of the async function body).
- Then microtasks in queue order (`.then`, `queueMicrotask`, the continuation after `await`).
- Then timer vs rAF: **either can come first**. The timer is a task; rAF belongs to the render step, and whether a frame is due before the timer task is picked is timing-dependent. "It depends, and here's why" is the senior answer.

## Code sketch
```ts
const yieldToMain = (): Promise<void> =>
  'scheduler' in globalThis && 'yield' in (globalThis as any).scheduler
    ? (globalThis as any).scheduler.yield()
    : new Promise((r) => setTimeout(r, 0));

async function runChunked<T>(items: T[], fn: (x: T) => void, sliceMs = 8) {
  let until = performance.now() + sliceMs;
  for (const item of items) {
    fn(item);
    if (performance.now() >= until) {
      await yieldToMain();
      until = performance.now() + sliceMs;
    }
  }
}
```
`scheduler.yield()` keeps the continuation's priority ahead of other queued tasks; `setTimeout(0)` puts you at the back of the line. Browser support for `scheduler.yield` varies; verify before relying on it.

## Trade-offs & pitfalls
- `await Promise.resolve()` is **not** a yield to the browser: it is a microtask and runs before render. You need a task boundary (`setTimeout`, `MessageChannel`, `scheduler.yield`).
- Microtask starvation: recursive `queueMicrotask` freezes the page like `while(true)`.
- Timer clamping: nested timers get a ~4 ms floor; background tabs throttle to ~1 s or worse. Never build a clock on `setTimeout`.
- `await` on a non-promise still defers to a microtask.
- Node differs: `process.nextTick` runs before promise jobs, and libuv phases (timers, poll, check) replace the render step.
- Chunking adds total time; a worker adds serialization cost and has no DOM. Pick based on whether the work needs the DOM.

## Likely follow-ups
- **How does React fit?** Its scheduler posts `MessageChannel` tasks and yields roughly every 5 ms during concurrent rendering, so input can land between slices; discrete/sync updates flush without yielding.
- **What's a long task?** Any task over 50 ms. Long Animation Frames (LoAF) API attributes slow frames to scripts; that's your INP debugging tool.
- **Where do IntersectionObserver callbacks run?** In the render steps after layout, batched per frame, not per scroll event.
- **Why does `setTimeout(fn, 0)` "fix" things?** It ends the current task, giving the browser a chance (not a guarantee) to render first.
- **Why rAF for animation?** It runs right before paint, so reads see this frame's layout and writes land in this frame.

## Say it in 60 seconds
The browser runs one task at a time to completion, then drains the entire microtask queue, then, if a frame is due, runs rAF callbacks, style, layout and paint. Rendering can only happen between tasks, so a long synchronous handler or an endless promise chain blocks paint and input. That's why setting a loading flag and then doing 400 ms of sync work never shows the spinner: there is no frame between the two state changes. The fix is to move the work to a worker or chunk it and yield at a real task boundary with `scheduler.yield` or `setTimeout`, not `await Promise.resolve()`, which is still a microtask. In the classic ordering puzzle, sync logs come first, then microtasks in order, and timeout vs rAF can swap because one is a task and the other belongs to the render step.
