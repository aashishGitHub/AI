# Design a collaborative document editor: OT vs CRDT, presence, offline and undo
**Round:** 12 · Frontend System Design · **Level:** Principal · **Time:** 30 min · **Tags:** system design · collaboration · crdt
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: Google-Docs-like editor with live cursors, offline editing and per-user undo.

## What they're really testing
Editor model choice, a defensible OT-vs-CRDT decision, separation of durable document state from ephemeral presence, reconnection/offline merge, and collaborative undo semantics, plus permissions enforced server-side.

## Core answer (key points)
- **Requirements:** rich text (headings, lists, links, images), co-editing with low perceived latency (target ~<200ms), presence cursors, comments, version history, offline edits merging on reconnect, permissions (view/comment/edit).
- **Editor model:** structured editor (ProseMirror, Lexical, Tiptap) with a schema; not raw `contenteditable` HTML, which is inconsistent across browsers and has no operation model.
- **OT vs CRDT:**

| | OT | CRDT (Yjs, Automerge) |
|---|---|---|
| Central ordering | required | not required (server = relay + storage) |
| Offline / long divergence | harder | natural |
| Metadata | low | higher (ids, tombstones; GC + binary encoding help) |
| Complexity | transform function per op pair | use a library; custom types are hard |
| Known users | Google Docs, ShareDB | many Yjs/Automerge apps |

- **Pragmatic choice for most teams:** Yjs + ProseMirror binding + WebSocket sync server + IndexedDB persistence.
- **Presence:** separate ephemeral channel (Yjs "awareness"): cursor, selection, name, colour. Not persisted. Throttle (~20/s), hide idle users, cap rendered cursors.
- **Sync:** on reconnect, exchange state vectors so only missing updates flow. Backoff on reconnect. UI: "Offline, changes saved locally"; `beforeunload` warning if local updates are not yet persisted anywhere.
- **Undo:** per user; only revert operations whose origin is this client (`UndoManager` with tracked origins); coalesce typing bursts (~500ms).
- **Permissions:** sync server authenticates the socket and rejects updates from viewers/commenters. Never trust the client.
- **Comments:** anchored with relative positions so anchors survive concurrent edits; threads stored separately from the doc.
- **Versions:** periodic encoded snapshots with author/time; restore = new operations, not history rewrite.
- **Large docs:** sub-documents lazy-loaded; server compacts update logs into snapshots; GC deleted content when safe.
- **Surprising merges:** concurrent format/delete merges are deterministic but can confuse; show attribution ("edited by"), rely on undo.

## Mental model / flow
```
┌──────────────────────────── Client ────────────────────────────┐
│ ProseMirror view ⇄ y-prosemirror binding ⇄ Y.Doc (CRDT state)   │
│      ▲ local tx (origin = me)            │  ▲                    │
│      │                                   │  │ remote updates     │
│  UndoManager (tracks origin=me only)     │  │                    │
│                                          ▼  │                    │
│                         y-indexeddb (persist every update)       │
│                         WebSocket provider ─────────────┐        │
│ Awareness (cursor, name, colour) ── ephemeral ──────────┤        │
└─────────────────────────────────────────────────────────┼────────┘
                                                          ▼
                    ┌──────────────── Sync server ──────────────────┐
                    │ authN socket · authZ: drop updates from viewers│
                    │ fan-out updates + awareness to room            │
                    │ append update log ─► compact ─► snapshot store │
                    └───────────────────────────────────────────────┘
Reconnect: client sends state vector ─► server returns only missing updates (and vice versa)
```

## Code sketch
```ts
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { IndexeddbPersistence } from 'y-indexeddb';

export function openDoc(docId: string, me: { name: string; color: string }, token: string) {
  const doc = new Y.Doc();
  const local = new IndexeddbPersistence(`doc:${docId}`, doc);           // instant load + offline
  const remote = new WebsocketProvider(SYNC_URL, docId, doc, { params: { token } });
  remote.awareness.setLocalStateField('user', me);                         // presence only
  const content = doc.getXmlFragment('content');
  const undo = new Y.UndoManager(content, { trackedOrigins: new Set([ySyncPluginKey]), captureTimeout: 500 });
  remote.on('status', ({ status }: { status: string }) => setSyncBadge(status));
  return { doc, content, undo, destroy: () => { remote.destroy(); local.destroy(); doc.destroy(); } };
}
```
(API names from y-websocket / y-indexeddb / y-prosemirror as I recall them; verify against current Yjs docs, especially `ySyncPluginKey` as the tracked origin.)

## Trade-offs & pitfalls
- CRDT doc growth: tombstones accumulate; need GC and snapshotting, and GC conflicts with keeping full version history.
- OT needs a reliable central server; offline for hours means a big transform backlog and more failure modes.
- Presence on the durable channel bloats storage and history; keep separate.
- Undo that reverts others' edits feels like data loss; scope to own origin.
- Client-side permission checks only hide UI; server must enforce.
- Rich embeds (tables, images) need schema support in both editor and CRDT binding.

## Likely follow-ups
- *Why not plain last-writer-wins on paragraphs?* Loses concurrent typing in the same paragraph; character-level merge is the point.
- *How do you show "who typed this"?* Attribution metadata per insert (Yjs supports attribution via snapshots/permanent user data; verify current API).
- *Scaling the sync server?* Room-sharded by doc id, sticky routing, pub/sub between nodes, persistence decoupled.
- *E2E encryption?* CRDTs fit (server only relays opaque updates), but server-side search/indexing is lost.
- *Measure?* Edit-to-remote-visible latency, reconnect success, conflict/undo rates, doc load time, snapshot size.

## Say it in 60 seconds
I'd build on a structured editor like ProseMirror or Lexical, not raw contenteditable. For concurrency there are two families. OT needs a central server to transform operations; it's what Google Docs does. CRDTs make operations commute so replicas merge anywhere, which suits offline and long divergence. For most teams I'd pick Yjs: a ProseMirror binding, IndexedDB persistence for instant load and offline, and a WebSocket sync server that authenticates, drops writes from viewers, fans out updates and compacts logs into snapshots. Presence travels on a separate ephemeral awareness channel, throttled. On reconnect, state vectors mean only missing updates are exchanged. Undo is per user, tracking only my origin. Comments anchor to relative positions, versions are snapshots, and restoring creates new ops. The main costs are CRDT metadata growth and needing GC.
