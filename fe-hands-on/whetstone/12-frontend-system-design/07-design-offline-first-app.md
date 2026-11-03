# Design an offline-first app: local database, sync queue, conflicts and service worker
**Round:** 12 · Frontend System Design · **Level:** Lead / Staff · **Time:** 25 min · **Tags:** system design · offline-first · sync
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: field-service app; technicians fill forms and attach photos offline for hours, sync later, sometimes editing the same record as the office.

## What they're really testing
Do you invert the architecture (local DB is truth, network is sync), design an idempotent outbox with ordering and partial-failure handling, pick conflict policies per data type, and handle storage, multi-tab and UX honestly?

## Core answer (key points)
- **Requirements:** create/edit inspections + photos offline for hours; multiple devices per user; occasional concurrent edits with office; never lose data; visible pending state.
- **Local DB is the source of truth for UI:** IndexedDB (via Dexie or similar) or SQLite-in-OPFS. UI uses live queries; it never waits on the network.
- **Write path:** in one local transaction, apply the change and append an op to an **outbox**. Op = `{ opId (UUID, idempotency key), entity, id (client UUID), kind, patch, baseVersion, at }`.
- **Client-generated ids** so offline-created records are referenceable before the server knows them.
- **Push:** sync engine drains the outbox when online, in order **per entity** (a stuck op blocks only its entity). Network/5xx → retry with exponential backoff + jitter. 4xx validation → move to "needs attention" list shown to the user.
- **Pull:** `GET /sync?since=cursor` returns a change log; apply in a transaction; then re-apply still-pending local ops on top (rebase) so the UI shows local intent.
- **Server idempotency:** dedupe by `opId`; return the stored result for retries.
- **Conflict policies per data type:**

| Data | Policy |
|---|---|
| independent fields (title, notes) | field-level last-writer-wins (server receive order or hybrid logical clock) |
| counters / sets | merge (PN-counter, add-wins set) |
| critical (approval status) | server wins; show conflict to user |
| rich text | CRDT (Yjs) |
| rare true conflicts | keep both, ask user |

- **Conflict detection:** server compares op's `baseVersion` with current version per field/record.
- **Photos:** blobs in IndexedDB/OPFS, chunked/resumable upload, records reference blob ids; record op can sync before blob finishes, with a "photo uploading" state.
- **Storage:** check `navigator.storage.estimate()`, request `navigator.storage.persist()` to reduce eviction risk; compress photos client-side.
- **Multi-tab:** Web Locks leader election so one tab runs sync; BroadcastChannel to notify others.
- **Service worker:** precache app shell + assets so it launches offline; Background Sync where supported (Chromium; not Safari as far as I know, verify), otherwise sync on `online` event / app open / interval.
- **Schema migrations:** versioned local DB migrations; outbox ops carry schema version; server accepts N-1 versions.
- **UX:** "All changes synced" / "3 changes waiting" / "Offline: saved on this device"; inline conflict resolution; never block editing.

## Mental model / flow
```
┌───────────────────────────────── Device ──────────────────────────────────┐
│ UI ◄── live queries ── Local DB (IndexedDB / SQLite-OPFS)                  │
│  │ edit                    ▲            ▲                                   │
│  └─► tx{ apply change ; append Op } ──► Outbox [op1, op2, ...]               │
│                            │            │ drain (per-entity order, backoff)  │
│                            │ apply+rebase                                    │
│                  Sync engine (leader tab via Web Locks) ───────────────────┐ │
│                            ▲                                               │ │
│ Blob store (photos) ── chunked upload ─────────────────────────────────────┤ │
│ Service worker: precache shell · Background Sync (where supported)         │ │
└────────────────────────────────────────────────────────────────────────────┼─┘
                    POST /sync/push {ops}   ◄── dedupe by opId, check baseVersion
                    GET  /sync/pull?since=cursor ──► change log + new cursor
                                         Server ─► conflict policy per entity/field
```

## Code sketch
```ts
interface Op { opId: string; entity: 'inspection' | 'photo'; id: string; kind: 'create' | 'update' | 'delete';
  patch?: Record<string, unknown>; baseVersion: number | null; at: number; }

export async function saveInspection(db: LocalDb, id: string, patch: Partial<Inspection>) {
  await db.transaction('rw', db.inspections, db.outbox, async () => {
    const cur = await db.inspections.get(id);
    await db.inspections.put({ ...cur!, ...patch, _pending: true });
    await db.outbox.add({ opId: crypto.randomUUID(), entity: 'inspection', id, kind: 'update',
      patch, baseVersion: cur?._serverVersion ?? null, at: Date.now() });
  });
}

export async function runSync(db: LocalDb, api: SyncApi) {
  await navigator.locks.request('sync', { ifAvailable: true }, async lock => {
    if (!lock) return;                                // another tab is the leader
    const blocked = new Set<string>();
    for (const op of await db.outbox.orderBy('at').toArray()) {
      if (blocked.has(op.id)) continue;               // keep per-entity order
      const r = await api.push(op).catch(() => ({ status: 'retry' as const }));
      if (r.status === 'ok') await db.outbox.delete(op.opId);
      else if (r.status === 'rejected') { await db.needsAttention.add({ ...op, reason: r.reason }); await db.outbox.delete(op.opId); }
      else blocked.add(op.id);                        // retry later with backoff
    }
    await api.pullInto(db);                           // apply change log, then rebase pending ops
  });
}
```

## Trade-offs & pitfalls
- LWW by device clock is wrong when clocks drift; use server order or hybrid logical clocks.
- Whole-record LWW loses concurrent edits to different fields; go field-level.
- Safari historically evicted script-writable storage after periods of non-use; `persist()` and installed PWA status matter. Verify current WebKit policy.
- Outbox growing unbounded when a 4xx op blocks forever; must surface it.
- Pulling without rebasing pending ops makes UI flicker back to server state until push succeeds.
- Migrations that run in one tab while another tab still has an old schema open; handle `versionchange` events.

## Likely follow-ups
- *Why not just cache GET responses in the SW?* That's offline-readable, not offline-first; writes still need the outbox and conflict logic.
- *How to test?* Network throttling/offline in DevTools, Playwright `context.setOffline`, fault injection on push (5xx, timeouts, duplicate delivery), clock skew.
- *Auth tokens expire while offline?* Queue continues; on reconnect refresh first; if refresh fails, keep data and prompt re-login without wiping.
- *Deletes vs edits conflict?* Tombstones; policy decides whether edit resurrects or delete wins.
- *Off-the-shelf?* Replicache/Zero, PowerSync, ElectricSQL, RxDB, WatermelonDB exist; evaluate vs bespoke (verify current state of each).

## Say it in 60 seconds
Offline-first flips the architecture: the local database, IndexedDB or SQLite in OPFS, is the UI's source of truth, and the network is just a sync channel. Every edit applies locally and appends an operation to an outbox in the same transaction. Each op has a UUID idempotency key, a client-generated record id and the base version it edited from. A sync engine, run by one leader tab via Web Locks, pushes ops in order per entity with backoff, and moves validation failures to a visible "needs attention" list. It pulls a change log since a cursor and rebases pending local ops on top. The server dedupes by op id and detects conflicts by base version, with a policy per data type. Photos are stored as blobs with resumable upload, the service worker precaches the shell, and the UI always says what's pending.
