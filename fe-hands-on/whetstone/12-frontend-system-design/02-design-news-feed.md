# Design a news feed (Twitter/LinkedIn-style): rendering, pagination, real-time inserts and media
**Round:** 12 · Frontend System Design · **Level:** Lead / Staff · **Time:** 30 min · **Tags:** system design · news feed · pagination
Source: https://whetstone-v1.vercel.app/#frontend-system-design

Scenario: infinite scroll, "new posts" indicator, likes, comments, images and video, web + mobile.

## What they're really testing
Rendering strategy for first paint, a normalized cache that keeps entities consistent, real-time inserts that don't move the reader, variable-height virtualization, and optimistic writes with race handling.

## Core answer (key points)
- **Requirements:** view feed, infinite scroll, compose (text + images), like/comment, new-post signal, post detail. NFRs: fast first paint on mid mobile, smooth scroll (INP, no jank), flaky networks, accessible; ranking is server-side.
- **Rendering:** SSR/stream the first page for LCP; hydrate; continue client-side with cursor pagination.
- **Pagination:** opaque cursor (not offset); offsets break when new posts shift the list. Prefetch the next page about two screens before the end.
- **Normalized cache:** `posts`, `users`, `media` keyed by id; feed pages hold only ids. A like updates one entity and every view of it (feed, detail, profile) re-renders consistently.
- **Real-time:** SSE (one-way, auto-reconnect, HTTP-friendly) or polling sends "N new posts"; buffer ids in `pendingNewIds`; show a pill; prepend only on click (or auto-insert if already at top). Never shove content above the viewport mid-read.
- **Virtualization:** variable heights → estimate, measure on render, scroll anchoring when items above change height. Reserve image boxes with `aspect-ratio` from server-provided width/height so measurement is stable (also kills CLS).
- **Optimistic like:** update cache, fire request, reconcile with server truth, roll back + toast on failure. Rapid taps race: send desired state (`PUT like {liked:true}`) which is idempotent, or serialise per post keeping only latest intent.
- **Compose:** upload media direct to object storage via presigned URL with progress; create the post after uploads finish; `Idempotency-Key` on create so retries don't double-post.
- **Media:** CDN-resized `srcset`, AVIF/WebP, lazy below fold, blur placeholders, video `preload="none"` + poster, autoplay muted only when in view (IntersectionObserver).
- **A11y:** `role="feed"` with `article` items, `aria-setsize`/`aria-posinset` (use -1 for unknown size), focus management when the pill reveals posts, optional j/k shortcuts.
- **Long sessions:** cap memory by evicting far-off pages from the cache.
- **Observability:** feed TTFB/LCP, long animation frames while scrolling, like/post error rates, SSE connection health, engagement.

## Mental model / flow
```
┌──────────────────────── Browser ─────────────────────────┐        ┌────────── Edge / Server ──────────┐
│ FeedPage                                                 │        │ SSR/stream first page (HTML+data) │
│  ├─ Composer ──(optimistic create, Idempotency-Key)──────┼──POST──▶ BFF /posts                        │
│  │    └─ media ──(presigned PUT)─────────────────────────┼────────▶ Object storage ─► Media CDN       │
│  ├─ NewPostsPill ◀── pendingNewIds ◀─────────────────────┼◀─SSE──── /feed/stream  event:new_posts    │
│  ├─ VirtualFeed (measure, anchor, prefetch @2 screens)   │        │                                   │
│  │    └─ PostCard (memo; reads entity by id)             │        │                                   │
│  │         └─ LikeButton ──(optimistic, PUT desired)─────┼──PUT───▶ /posts/:id/like                   │
│  └─ Normalized cache {posts, users, media, feed.pages}◀──┼◀─GET─── /feed?cursor=…&limit=20           │
└──────────────────────────────────────────────────────────┘        └───────────────────────────────────┘
Data: server → cache (entities) → selectors → cards.  Control: scroll position drives fetch; SSE only signals.
```

## Code sketch
```ts
interface Post { id: string; authorId: string; text: string; mediaIds: string[]; likeCount: number; likedByMe: boolean; }
interface FeedState {
  posts: Record<string, Post>;
  users: Record<string, { id: string; name: string; avatarUrl: string }>;
  pages: { ids: string[]; nextCursor: string | null }[];
  pendingNewIds: string[];
}

const inflight = new Map<string, AbortController>();
export function setLiked(store: Store<FeedState>, id: string, liked: boolean) {
  const prev = store.get().posts[id];
  store.patchPost(id, { likedByMe: liked, likeCount: prev.likeCount + (liked ? 1 : -1) });
  inflight.get(id)?.abort();                          // latest intent wins
  const ctl = new AbortController(); inflight.set(id, ctl);
  api.put(`/posts/${id}/like`, { liked }, { signal: ctl.signal })
    .then(server => store.patchPost(id, server))
    .catch(e => { if (e.name !== 'AbortError') { store.patchPost(id, prev); toast('Could not update like'); } });
}
```
(Aborting only cancels the client wait; the server may still apply it. Sending desired state keeps the final result correct anyway.)

## Trade-offs & pitfalls
- SSE vs WebSocket: SSE suffices for one-way "new posts"; WebSocket when you also need client→server realtime (typing, presence). HTTP/1.1 limits concurrent SSE per origin (around 6); HTTP/2 removes that in practice.
- Virtualization breaks find-in-page and some SR navigation; `role="feed"` + keeping a small overscan helps.
- Evicting pages breaks "scroll back up" unless you can refetch by cursor.
- Toggle-style like endpoints are non-idempotent; retries flip state.
- SSR + personalization: first page HTML is per user, so it can't be CDN-cached; stream it from the edge.

## Likely follow-ups
- *Why cursor not offset?* Inserted posts shift offsets (dupes/skips); cursors are stable and index-friendly.
- *Restore scroll on back from post detail?* Keep cache + store scroll offset and anchor item id; re-measure on return.
- *Comments threads?* Lazy-load per post; same normalized pattern; optimistic create with temp id swapped on success.
- *Offline?* Cache last N pages in IndexedDB, queue likes/posts in an outbox.
- *What would you build first?* SSR page + cursor pagination + normalized cache; then virtualization; then realtime pill.

## Say it in 60 seconds
I'd server-render the first page for LCP, hydrate, then load more by opaque cursor, prefetching about two screens early. Data lives in a normalized cache, so posts, users and media are stored by id and pages are just id lists. One like updates every view of that post. New posts arrive as an SSE signal into a pending buffer behind a "3 new posts" pill, so content never jumps above the reader. The list is virtualized with measured variable heights and scroll anchoring, and images reserve space by aspect ratio. Likes are optimistic, sending the desired state so retries are idempotent, with rollback on failure. Media uploads go direct to storage via presigned URLs, and posts carry idempotency keys. Add `role="feed"`, memory caps for long sessions, and scroll-jank and error metrics.
