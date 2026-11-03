# 06 · Machine Coding
> Timed UI builds at a senior bar: typeahead, virtual list, modal, OTP, undo/redo, infinite feed, accurate timers, uploader, kanban, queued progress bars · 10 questions · ~5 h 50 min
Source: https://whetstone-v1.vercel.app/#machine-coding

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Build an accessible typeahead (combobox) with debounced search and race-safe results | Senior | 45 min | machine coding · combobox · autocomplete | [notes](01-accessible-typeahead-combobox.md) |
| 02 | Build a virtualized list from scratch (fixed and variable row heights) | Lead / Staff | 40 min | virtualization · windowing · performance | [notes](02-virtualized-list-from-scratch.md) |
| 03 | Build a modal dialog: focus trap, scroll lock, stacking, and why <dialog> helps | Senior | 30 min | modal · dialog · focus management | [notes](03-modal-dialog-focus-trap.md) |
| 04 | Build an OTP input: paste, backspace, autofill and accessibility | Senior | 25 min | otp · inputs · paste | [notes](04-otp-input-paste-autofill.md) |
| 05 | Add undo/redo to an editor: command pattern vs snapshots, coalescing, and limits | Lead / Staff | 30 min | undo · redo · command pattern | [notes](05-undo-redo-command-vs-snapshot.md) |
| 06 | Infinite scrolling feed: cursor pagination, IntersectionObserver and scroll restoration | Senior | 35 min | infinite scroll · pagination · intersectionobserver | [notes](06-infinite-feed-cursor-pagination.md) |
| 07 | Build an accurate countdown or stopwatch that survives background tabs | Senior | 20 min | timers · setinterval · drift | [notes](07-accurate-countdown-stopwatch-timer.md) |
| 08 | Build a file uploader with concurrency, progress, cancel and retry | Lead / Staff | 35 min | uploads · progress · xhr | [notes](08-file-uploader-concurrency-progress.md) |
| 09 | Build a Trello-style kanban board: lists, cards, drag and drop between lists, persisted on reload | Lead / Staff | 60 min | machine coding · kanban · drag and drop | [notes](09-kanban-board-drag-and-drop.md) |
| 10 | Build progress bars that each fill in n seconds and run one after another when you click quickly | Senior | 30 min | machine coding · progress bar · queue | [notes](10-sequential-progress-bars-queue.md) |

## How these connect
- **Shared opening move for every build:** clarify scope (2 min) → state shape → pure logic (reducer / framework-free helper) → UI → a11y → edge cases → "production would use X". Interviewers grade structure as much as output.
- **Async correctness cluster:** 01 (debounce + abort, latest wins), 06 (single in-flight, dedupe, retry same cursor), 08 (concurrency pool, abort, retry policy), 10 (serial promise queue). Study 10 → 08 → 01 → 06; they reuse the same AbortSignal + queue ideas.
- **Time is derived, never counted:** 07 (deadline + monotonic clock) and 10 (rAF progress from elapsed time) are the same lesson.
- **Pure reducers make UIs testable:** 05 (history reducer) and 09 (board reducer); 05 can wrap 09 for undo.
- **Accessibility-heavy builds:** 01 (combobox, `aria-activedescendant`), 03 (`<dialog>`, inert, focus restore), 04 (grouped inputs, autofill), 09 (non-drag alternative, WCAG 2.5.7). Pair with round 05 Q01-Q02.
- **Scale/perf:** 02 (virtualization) underpins 06 and 09 at large sizes; pair with round 04 Q02.
