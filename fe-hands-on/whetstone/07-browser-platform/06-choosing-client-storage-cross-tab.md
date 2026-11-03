# Choosing client storage: cookies, localStorage, IndexedDB, OPFS, Cache API, and syncing across tabs
**Round:** 07 · Browser & Web Platform · **Level:** Senior · **Time:** 12 min · **Tags:** storage · indexeddb · localstorage
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: offline-capable notes app. Store auth session, UI preferences, ~50 MB of notes + attachments, and state shared between tabs.

## What they're really testing
Matching each data shape to the right store (size, sync/async, who can read it, worker access), plus durability (quota, eviction), cross-tab coordination, and security.

## Core answer (key points)
- **Auth session → cookie**, `HttpOnly; Secure; SameSite=Lax` (or Strict). JS can't read it, so XSS can't exfiltrate it. Not in localStorage.
- **UI preferences → localStorage.** Small, string-only, synchronous, survives restarts; fine for a few KB read at startup.
- **Notes + attachments (50 MB) → IndexedDB** (async, transactional, structured clone, stores Blobs, usable from workers). Use a wrapper (idb, Dexie). Alternative: **OPFS** (origin private file system) with SQLite-WASM in a worker if you want SQL and high write throughput.
- **Cached HTTP responses / app shell → Cache API**, typically driven by the service worker.
- **Per-tab drafts → sessionStorage** (scoped to the tab; survives reload, not close).
- **Durability:** default storage is "best-effort" and evictable under pressure. Call `navigator.storage.persist()` for offline notes; monitor `navigator.storage.estimate()`; handle `QuotaExceededError`.
- **Cross-tab:** `storage` event fires in *other* tabs on localStorage change (good for small state); `BroadcastChannel` for explicit messages; **Web Locks** (`navigator.locks.request`) so only one tab runs a sync job or token refresh.
- **Versioning/migration:** IndexedDB has `onupgradeneeded` with a version number; for localStorage, store a schema version and validate (e.g. zod) on read because data may be from an older build.

## Mental model / flow
| Store | Size (approx.) | API | Sent to server | In workers | Good for |
|---|---|---|---|---|---|
| Cookie | ~4 KB each | sync string | yes, every request | no (cookieStore API partial) | session id |
| sessionStorage | ~5 MB | sync | no | no | per-tab draft |
| localStorage | ~5 MB | sync | no | no | prefs, flags |
| IndexedDB | quota (large) | async | no | yes | offline data, blobs, outbox |
| OPFS | quota (large) | async; sync handles in workers | no | yes | SQLite-WASM, big files |
| Cache API | quota (large) | async | no | yes | Request/Response pairs |

Sizes are approximate and browser-dependent; verify current quotas on MDN.

## Code sketch
```ts
// One writer for sync across tabs, notify the rest.
const bus = new BroadcastChannel('notes');

export async function syncNotes() {
  await navigator.locks.request('notes-sync', async () => {
    const pending = await db.getAll('outbox');
    for (const op of pending) {
      await api.push(op);
      await db.delete('outbox', op.id);
    }
  });
  bus.postMessage({ type: 'notes:synced' });
}

bus.onmessage = (e) => {
  if (e.data?.type === 'notes:synced') void refreshFromDb();
};

export function readPrefs(): Prefs {
  try {
    const parsed = PrefsSchema.safeParse(JSON.parse(localStorage.getItem('prefs') ?? '{}'));
    return parsed.success ? parsed.data : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}
```

## Trade-offs & pitfalls
- **localStorage is synchronous** and blocks the main thread; serializing big objects on every keystroke shows up as jank/INP.
- **Safari ITP** can cap script-writable storage (~7 days without user interaction) in some contexts; installed PWAs are treated differently. Verify current WebKit policy.
- **Private mode / sandboxed iframes / disabled storage** can throw on access; wrap every access in try/catch and degrade.
- **Never store** long-lived tokens, secrets, or unencrypted sensitive PII client-side if avoidable; anything JS can read, XSS can read.
- **IndexedDB pitfalls:** transactions auto-commit when the event loop idles (don't `await` unrelated network inside a transaction); blocked upgrades when an old tab holds the DB open (handle `onversionchange` by closing).
- **Clear on logout:** IndexedDB, Cache API, localStorage keys tied to the user.
- **BroadcastChannel** is same-origin, doesn't persist; a tab opened later must read from storage, not rely on messages.

## Likely follow-ups
- **Why not just localStorage for notes?** 5 MB string-only cap, sync I/O, no transactions, no blobs, not available in workers.
- **OPFS vs IndexedDB?** OPFS gives file semantics and fast synchronous access handles in workers (ideal for SQLite-WASM); IndexedDB is simpler for object-shaped data.
- **How do you handle a schema change?** Bump the IndexedDB version and migrate in `onupgradeneeded`; for localStorage, version key + migrate-or-reset.
- **Leader election across tabs?** Hold a Web Lock for the tab's lifetime; whoever holds it is leader; others queue and take over automatically when it closes.
- **Encryption at rest?** Web Crypto with a non-extractable key in IndexedDB protects against casual disk access, not against XSS in the same origin.

## Say it in 60 seconds
I split by data shape. The auth session lives in an HttpOnly, Secure, SameSite cookie, so JavaScript and therefore XSS can't read it. Preferences go in localStorage because they're tiny and read synchronously at startup. The 50 MB of notes and attachments go in IndexedDB, which is async, transactional, stores blobs and works in workers; OPFS with SQLite-WASM is the alternative if we want SQL. The service worker uses the Cache API for the shell. I request persistent storage so offline notes aren't evicted, handle quota errors, and version and validate everything I read. For tabs, BroadcastChannel announces changes and Web Locks makes sure only one tab runs sync or token refresh at a time. And on logout I clear every store tied to the user.
