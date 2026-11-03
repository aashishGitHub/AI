# RAG product UX: citations, confidence, empty answers and feedback loops
**Round:** 14 · AI-Powered Frontends · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** rag · citations · ux
Source: https://whetstone-v1.vercel.app/#ai-frontend

Scenario: an internal-docs assistant loses user trust after a few wrong answers. Make answers checkable and failures graceful.

## What they're really testing
Designing for verifiability and honest failure, and closing the loop so feedback actually improves retrieval and evals.

## Core answer (key points)
- **Trust = checkability.** RAG (retrieval-augmented generation: fetch relevant chunks, then generate from them) is only as good as its sources, so make sources visible.
- **Inline citations** `[1]` next to claims -> source card: title, highlighted snippet, last-updated date, deep link to the exact passage. Plus a sources panel.
- **Honest empty/low-confidence state:** "I couldn't find this in the docs; here are the closest articles" and an escalation (search, human). Beats a confident hallucination.
- **Separate retrieved facts from model reasoning** visually.
- **Scope indicator:** which corpus was searched, with filters to change it.
- **Conflicting or stale sources:** surface both with dates rather than silently picking one.
- **Permission-aware:** retrieval filters by the user's access server-side; never cite a doc the user can't open (it also leaks existence).
- **Feedback:** thumbs with reason categories (wrong, outdated, missing source, unhelpful), "report this source".
- **Log for diagnosis (privacy-aware):** query, retrieved doc ids + scores, cited ids, answer id, latency per stage, feedback. This tells you if a failure is retrieval (wrong chunks) or generation (ignored good chunks).
- **Perceived speed:** show "Searching N sources..." within ~200 ms, stream the answer, lazy-render source cards. Time to first token is the key metric.

## Mental model / flow
```
query -> [retrieve (ACL-filtered)] -> chunks+scores -> [generate w/ citations] -> stream
                     |                                         |
                 log ids/scores                       citation events -> source cards
user feedback -> joined with logs -> triage: retrieval vs generation -> eval set grows
```

## Code sketch
```tsx
// Own sketch: citation marker that never shifts layout and opens a source card
function Citation({ n, source }: { n: number; source?: Source }) {
  return (
    <sup>
      <button aria-label={`Source ${n}${source ? `: ${source.title}` : ''}`}
              className="cite" disabled={!source}
              onClick={() => openSource(source!)}>
        [{n}]
      </button>
    </sup>
  );
}
```

## Trade-offs & pitfalls
- Citations arriving after the text cause reflow; reserve space or render markers as they arrive.
- A citation that points to a whole 40-page doc is not checkable; link to the passage.
- Displaying numeric "confidence %" invites false precision; I'm not aware of a reliable calibrated confidence score from LLMs, so prefer qualitative states (found / partial / not found) driven by retrieval scores.
- Thumbs-down without reasons is weak signal; keep reasons to a few one-click options.
- Logging queries may capture sensitive data; minimize, redact, set retention.

## Likely follow-ups
- **How do you measure trust?** Citation click-through, thumbs ratio, repeat usage, escalation rate, "answer then search anyway" rate.
- **How does feedback reach the model?** Not directly; it feeds an eval set and retrieval tuning (chunking, ranking), reviewed by humans.
- **What if sources are outdated?** Show dates, prefer fresher docs in ranking, flag stale content to doc owners.
- **Hallucinated citations?** Validate that cited ids exist in the retrieved set before rendering.

## Say it in 60 seconds
People trust a docs assistant when they can check it. So every claim carries an inline citation that opens a card with the highlighted passage, date and a deep link, and there's a sources panel and a clear indicator of which corpus was searched. When retrieval finds nothing good, the assistant says so and offers the closest articles or a human, instead of guessing. Retrieval is permission-filtered on the server. Feedback has a few reason categories, and we log which documents were retrieved and cited with per-stage latency, so we can tell retrieval failures from generation failures and grow the eval set. For speed, show searching progress quickly, stream the answer and lazy-load source cards.
