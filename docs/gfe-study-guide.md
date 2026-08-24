# GreatFrontEnd Study Guide — Scanned Aug 22, 2026

Scanned: system design question bank, full React Interview Playbook (all 12 articles), React interview question bank (92 questions), filtered for UI coding + React medium/hard, plus SSR coverage. Mapped to your existing Tier 1 rampup (F1–F11 in `career-roadmap.md`) and Tue/weekend GFE slots.

---

## 1. React Interview Playbook — 12 articles (free, no paywall)

| # | Article | One-line | Priority |
|---|---|---|---|
| 1 | [Introduction](https://www.greatfrontend.com/react-interview-playbook/introduction) | Question types + strategy overview | Skim once |
| 2 | [Landscape & history](https://www.greatfrontend.com/react-interview-playbook/react-landscape-history) | React's evolution, ecosystem | Skip — you lived through this |
| 3 | [How to prepare](https://www.greatfrontend.com/react-interview-playbook/react-interview-preparation) | Step-by-step prep plan | Skim once |
| 4 | [Basic concepts](https://www.greatfrontend.com/react-interview-playbook/react-basic-concepts) | Components, JSX, props, state, rendering | Skip — refresher only if rusty |
| 5 | [Thinking declaratively](https://www.greatfrontend.com/react-interview-playbook/react-thinking-declaratively) | Declarative vs imperative, todo-list example | Skim once |
| 6 | **[State design](https://www.greatfrontend.com/react-interview-playbook/react-state-design)** | How to structure/reset/derive state | **Read fully — below** |
| 7 | **[Hooks](https://www.greatfrontend.com/react-interview-playbook/react-hooks)** | useState/useEffect/useContext/useRef/useId pitfalls | **Read fully — below** |
| 8 | [Event handling](https://www.greatfrontend.com/react-interview-playbook/react-event-handling) | Synthetic events, keyboard/mouse/form | Read once |
| 9 | [Forms](https://www.greatfrontend.com/react-interview-playbook/react-forms) | Controlled vs uncontrolled, validation | Read once |
| 10 | [Signup form example](https://www.greatfrontend.com/react-interview-playbook/react-signup-form-example) | Worked accessible form example | Read alongside #9 |
| 11 | **[Data fetching](https://www.greatfrontend.com/react-interview-playbook/react-data-fetching)** | CSR patterns, race conditions, **CSR vs SSR** | **Read fully — below, SSR section** |
| 12 | **[Design patterns](https://www.greatfrontend.com/react-interview-playbook/react-design-patterns)** | HOC, render props, container/presentational | **Read fully — below** |

**Read order for your gaps:** 6 → 7 → 12 → 11 → 8 → 9/10. You already have 12 years of React; skip 1–5 unless you want a 10-minute refresher.

### State design (#6) — the interview-specific rules
- Keep state as local as possible; lift only when siblings need it.
- Group related fields into one object (`{x, y}` not two `useState`s) — prevents drift.
- Replace multiple booleans (`isSubmitting`/`isSubmitted`/`isError`) with one `status` enum — booleans allow contradictory states, an enum can't.
- Derive, don't store: if a value is computable from existing state (`count = todos.length`), compute it at render, don't sync it with an effect.
- To fully reset a component, change its `key` — React unmounts/remounts, clearing every hook.
- **For interviews specifically:** state almost always lives at the top; you probably won't need Context (prop-drilling 2–3 levels is fine at this scale); you probably won't need `useReducer` (exception: games).

### Hooks (#7) — the pitfalls that actually get probed
- `setCount(count + 1)` reads a stale closure — always prefer `setCount(prev => prev + 1)` when the next value depends on the last.
- Never mutate state in place (`user.age = 26`) — React compares by reference, so the re-render silently doesn't happen. Always spread into a new object.
- `useEffect`: pause before reaching for it in an interview — most self-contained UI questions don't need it. If you do, get the dependency array right (missing deps → stale closures; object/array deps recreated every render → effect fires needlessly, fix with `useMemo`; always return a cleanup function for intervals/subscriptions).
- Rules of hooks: same order every render — never call hooks inside conditions, loops, after an early `return`, or inside event handlers.
- Custom hooks: only worth being a hook if it calls another hook internally; otherwise it's a plain function.

### Design patterns (#12) — know these, lead with hooks
- HOC and render props are pre-hooks patterns for sharing logic — mention them, but say a custom hook is the modern default. HOCs/render props still matter for legacy class-component code.
- Container/presentational split (data-fetching container, dumb presentational component) is the same idea as backend layering (service vs. controller) — good architect-framing line for interviews.

---

## 2. SSR / Next.js — what GFE says, and how it maps to your Udemy course

GFE's own framing (from the Data Fetching article): **most React coding rounds stay client-side** (`useEffect` + `fetch`), but **CSR vs SSR is a standard system-design-round topic**, and take-homes may expect SSR.

Key facts to hold as talking points:
- SSR fetches data on the server before sending HTML — no client loading spinner, better SEO, better for personalized/request-specific content (auth, geolocation).
- Next.js does this via `getServerSideProps` (Pages Router, legacy) or **Server Components** (App Router, current) — your Udemy course should be teaching the App Router version; if it's still Pages-Router-first, flag it as dated per your own "2025+ only" rule in `RAMPUP.md`.
- Query libraries (TanStack Query, SWR) solve what hand-rolled `useEffect` fetching doesn't: caching, deduping, cancellation, optimistic-update rollback, background refetch. Naming one and what it buys you is a good signal in an interview, even in a plain-React round.
- Race conditions in client fetching (a slow response for an old query overwriting a fresh one) need an `AbortController` or an ignore-flag — debouncing alone does not fix this. This is a sharp, concrete thing to say out loud if a live-search question comes up.

**Action for today's Next.js/Udemy time:** when you get to your course's data-fetching module, explicitly map it against this list — Server Components vs `getServerSideProps`, streaming SSR, Suspense boundaries — and note in `career-roadmap.md` Tier 1 #2 whether you've now *shipped*, not just *studied*, an RSC feature (your own honesty rule, still open per `screening-prep.md`).

---

## 3. System design questions (19 total) — mapped to your F1 rotation

career-roadmap.md names news feed, autocomplete, infinite scroll, and chat app as your GFE system-design rotation. Here's the full bank with difficulty, so you can sequence the rest after those four.

**Medium (do these first — faster reps, still real trade-off depth):**
- [News Feed](https://www.greatfrontend.com/questions/system-design/news-feed-facebook) — accessibility, performance ← **your Wk1 pick**
- [Autocomplete](https://www.greatfrontend.com/questions/system-design/autocomplete) — accessibility, UI component ← **your Wk2 pick**
- [E-commerce Marketplace](https://www.greatfrontend.com/questions/system-design/e-commerce-amazon) — SEO, forms
- [Travel Booking (Airbnb)](https://www.greatfrontend.com/questions/system-design/travel-booking-airbnb) — perf, SEO
- [Photo Sharing (Instagram)](https://www.greatfrontend.com/questions/system-design/photo-sharing-instagram) — a11y, networking, perf
- [Dropdown Menu](https://www.greatfrontend.com/questions/system-design/dropdown-menu) — a11y, UI component
- [Image Carousel](https://www.greatfrontend.com/questions/system-design/image-carousel) — a11y, perf
- [Modal Dialog](https://www.greatfrontend.com/questions/system-design/modal-dialog) — a11y, UI component
- [Data Table](https://www.greatfrontend.com/questions/system-design/data-table) — a11y, UI component, large datasets
- [Poll Widget](https://www.greatfrontend.com/questions/system-design/poll-widget) — UI component
- [Email Client (Outlook)](https://www.greatfrontend.com/questions/system-design/email-client-outlook) — networking

**Hard (the complex-UI/architect tier — this is your #1b differentiator per career-roadmap.md):**
- [Pinterest](https://www.greatfrontend.com/questions/system-design/pinterest) — masonry layout, perf
- [Rich Text Editor](https://www.greatfrontend.com/questions/system-design/rich-text-editor) — perf, UI component
- [Google Docs](https://www.greatfrontend.com/questions/system-design/collaborative-editor-google-docs) — **OT vs CRDT, this is F3 material**
- [Design/Drawing Tool (Figma/Excalidraw)](https://www.greatfrontend.com/questions/system-design/design-drawing-tool-figma-canva) — **canvas rendering, this is F2 material**
- [Video Streaming (Netflix)](https://www.greatfrontend.com/questions/system-design/video-streaming-netflix) — networking, perf
- [Chat App (Messenger)](https://www.greatfrontend.com/questions/system-design/chat-application-messenger) — networking ← **your rotation's chat app pick**
- [Music Streaming (Spotify)](https://www.greatfrontend.com/questions/system-design/music-streaming-spotify) — offline support, queueing
- [Video Conferencing (Zoom)](https://www.greatfrontend.com/questions/system-design/video-conferencing-zoom) — networking, perf
- [Google Sheets](https://www.greatfrontend.com/questions/system-design/collaborative-spreadsheet-google-sheets) — networking, perf, UI component

**Note:** "infinite scroll" and "autocomplete" aren't listed as standalone *system-design* entries anymore — they now live as **UI coding** questions (see §4) plus concepts folded into News Feed / Autocomplete system design. Your F1 rotation naming "infinite scroll" as week 3 should point at the UI-coding version, not a separate system-design one.

---

## 4. React question bank (92 total) — UI coding, medium/hard, filtered

Full list is paywalled beyond previews, but titles/difficulty are public. Priority picks for your F11 drill slot (45 min, timed) and F1b complex-UI track:

**Medium — core reps (do these across your 3x/week F11 slots):**
Todo List, Tabs, Accordion, Star Rating, Stopwatch, Like Button, Image Carousel, Traffic Light, Digital Clock, File Explorer, Tic-tac-toe, Transfer List, Data Table, Data Table II, Modal Dialog, Analog Clock, Dice Roller, Signup Form, Users Database, Whack-A-Mole, Memory Game.

**Hard — save for once your rust is off, these are the differentiator tier:**
Image Carousel III (minimal DOM footprint), Tic-tac-toe II (N×N generalized), Transfer List II (bulk select), Nested Checkboxes (parent-child logic), Data Table III/IV (generalized, sort+filter), Selectable Cells (drag-select grid), Wordle, Auth Code Input, Progress Bars IV (pause/resume).

**Hook-building questions** (pairs well with your F7/F8 custom-hooks depth): `useDebounce`, `useEventListener`, `useClickOutside`, `useWindowSize`, `useMediaQuery`, `useInterval`, `useIdle` — these are the exact primitives a streaming/agent-console UI (your capstone) actually needs, so building them doubles as capstone infrastructure.

**Recommended order for today's stretch drill:** pick one **Medium** you haven't done, 45 min timed, no lookups until you're stuck for 10+ min. Since you said you're rusty — Todo List or Tabs are the gentlest re-entry; Star Rating or Like Button if you want something with a touch of animation/state-derivation practice tied to today's SSE work.

---

## Where this plugs into your existing plan
- **Tue slot (career-roadmap.md F1–F3):** work top-down through the Medium system-design list above, then the Hard/complex-UI tier (Pinterest, Google Docs, Figma-style tool) once the basics are cold.
- **F11 (3x/week UI coding drill):** pull from the Medium list above in order; treat Hard ones as a monthly stretch, not weekly.
- **Frontend Rampup F4/F5 (RSC + typed SDK) and Tier 1 #2 (React 19/Next.js):** use the SSR section above as your checklist while going through the Udemy course — confirm it's teaching Server Components/App Router, not the legacy Pages Router.