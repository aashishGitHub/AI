# STAR stories — DevRev FDE

Built only from evidence: commit subjects, ticket ids, code, and measured runs. Anything I could not verify is a
`[you: …]` slot — fill it from memory or cut it. Never improvise a number in the room.

Lanes: **[P]** shipped at Couchbase · **[L]** your own build. Authorship rule (from `docs/notes/career-roadmap.md`):
say "I built" only where you wrote the code; otherwise "I contributed" / "my part was".

Each story: the prompts it answers → STAR → a 60-second version → the boundary to hold.

---

## 1. The contract was wrong — Workato / NetSuite invoices [P] ⭐ lead story

**Answers:** "Tell me about an integration with a third-party system." · "A time requirements were ambiguous." ·
"How do you handle an unreliable upstream?"

- **S:** Capella customers needed their invoices in the product. NetSuite was the source of truth, reachable only
  through Workato recipes. `[you: who asked for it, and why it mattered]`
- **T:** Own the integration end to end: Go client, domain service, cp-api endpoint, UI (AV-141747, AV-144242,
  AV-145301–145303).
- **A:**
  - Tested the handed-over contract against the live recipe before trusting it: the PDF field is `presigned_url`,
    not the `presignedurl` it was documented as.
  - Sized our timeout to the upstream: 35 s, because Workato's own request timeout is 30 s.
  - Mapped Workato's **502/404** for "NetSuite hasn't generated the PDF yet" to a typed error and a customer
    message, instead of a "server error" that reads like an outage.
  - Security: the PDF recipe authorizes on invoice id alone, so the service checks the invoice belongs to the
    tenant first (IDOR). The HTTP client refuses redirects, because Go forwards custom headers like `api-token`
    across hosts. Bounded error-body reads. NetSuite URLs never reach the browser.
  - Shipped behind `enable-billing-invoices` (default off), RBAC on the route, MSW mocks, Cypress e2e.
- **R:** Merged as #58590 on 2026-10-16 behind the flag. `[you: rollout status — leave out if unknown]`

**60 s:** "The contract I was handed was a hypothesis, so I tested it against the real recipe first — the field
name was wrong and a 502 meant 'not generated yet', not an outage. I sized the timeout to Workato's own, closed an
IDOR the upstream left open, stopped the token leaking on redirects, and shipped it dark behind a flag with e2e
tests."

**Boundary:** no adoption numbers — say "shipped behind a flag".

---

## 2. Two bugs in my own eval harness [L]

**Answers:** "Hardest bug you've debugged." · "How do you know your AI system works?"

- **S:** Same model, same question, two harnesses (server vs eval) gave different answers: the eval path
  fabricated a SQL statement, the server path refused correctly.
- **T:** Find out which harness was lying before trusting any eval number.
- **A:**
  - Bug 1, prompt parity: the eval prompt said "use ONLY the context" with no permitted way to decline. Fixed with
    one sentence that gives the model a refusal string — "a prohibition without a permitted alternative is a trap."
  - Bug 2, found while verifying Bug 1: the 1.5B judge marked the now-correct refusal FAIL while its own reason
    agreed with it. Isolated it: fixed output, only the judge varied, 3 runs at temperature 0 → inverted 3/3. A 3B
    judge from the same family got it right 3/3. Swapped the judge.
  - Added a CI parity check so the two prompts can't drift again.
- **R:** The harness now grades correctly every time. The honest follow-up number: this 1B model complies about
  1 time in 5 on that question (6 runs, order-of-magnitude only).

**60 s:** "I don't trust a single eval run. Hold the input fixed, vary one thing, repeat. That's how I found the
judge inverting a correct verdict three times out of three."

**Boundary:** 2 golden cases is a seed; 6 runs is not a benchmark.

---

## 3. An eval that earned its keep on the first live run [L]

**Answers:** "How do you evaluate an agent?" · "Tell me about a time data changed your mind."

- **S:** I built a function-calling agent over MCP tools with a trajectory eval. The deterministic suite was 13/13,
  but that proves plumbing, not model behaviour.
- **T:** Find out how a real small model behaves before claiming anything.
- **A:** Ran `qwen2.5:3b` live, 5 runs × 12 cases. Read the audit logs for every failure before believing the
  score.
- **R:** 82% task success, 0 safety failures, and two real failures, each 0/5: the model **invented a tenant id**
  instead of asking, and it explained the **suppressed** alert instead of the firing root cause.
  `[updated with the fix and the re-measured numbers in agent-lab/NOTES.md "Live run" — quote those]`

**60 s:** "Green deterministic tests told me the harness worked. The first live run told me the model guesses
missing arguments. That's exactly what an eval is for."

**Boundary:** one model, small n, local CPU.

---

## 4. A user-visible error that wasn't an error [P]

**Answers:** "Error surfacing." · "A small change with outsized customer impact."

- **S:** The Capella UI polls metadata. Transient 504s from that poll raised a "Server error" toast — users saw
  an outage that wasn't one. `[you: how it was noticed — ticket, customer, on-call]`
- **T:** Stop the false alarm without hiding real failures.
- **A:** AV-144356 (#56867, 2026-09-18): changed the React Query retry and error handling for that poll in
  `utils/react-query.ts` and `routes.utils.ts`, so a transient 504 no longer surfaces the toast.
  `[you: exact rule — retry count / which statuses]`
- **R:** `[you: outcome]`

**Pair it with story 1's 502 → "no PDF yet":** same principle twice — tell the customer what actually happened.

---

## 5. Migrating legacy definitions without breaking customers [P]

**Answers:** "Schema mapping / data migration." · "Backward compatibility."

- **S:** Customers had Search (FTS) index definitions in older shapes; the new React index builder had to import
  and edit them. `[you: scale, which customers hit it]`
- **T:** Accept old definitions without silently changing what they mean.
- **A (three commits, three edge cases):**
  - AV-90296 (#35949): import an index definition and pre-select the form from it.
  - AV-100609 (#46084, 2025-11-07): `migrateIndex` crashed on a **null** `sourceParams` — normalised it.
  - AV-125740 (#50061, 2026-03-25): added a mapping + normalization for the legacy `docid_prefix` shape.
- **R:** `[you: outcome]`

**60 s:** "Every migration bug I hit was a shape someone didn't expect — a null, an old field name. So I normalise
at the boundary, map legacy fields explicitly, and never guess."

---

## 6. Security as a habit, not a project [P]

**Answers:** "How do you think about security in integrations?"

- AV-92985 (#36886): fixed an XSS exposure in axios.
- AV-141051 (#57166, 2026-09-24): upgraded `@datadog/browser-logs` to v7 to fix prototype pollution.
- Billing invoices (#58590): percent-encoded a query parameter (`oid`) that was injectable; refused HTTP redirects
  so the Workato token can't leak; IDOR ownership check before the PDF call.

**60 s:** "In an integration the dangerous bugs are at the seams: a token that follows a redirect, an id the
upstream trusts blindly, a parameter you didn't encode. I check those by default."

---

## 7. Throughput: the weekly re-embed [P — contributor]

**Answers:** "A performance win." · "Large-scale data sync."

- Facts: Ask AI's weekly re-embed cron went from **5–6 h synchronous to ~20 min with 10 goroutines**; corpus
  2,667 docs → 7,597 chunks (≤1,000 tokens each).
- `[you: your exact part — career-roadmap marks Ask AI as "Contributor". Only say "I" for what you wrote.]`

---

## Slots with no evidence in any repo — pick a real one or skip

- **Disagreed with a stakeholder / customer** `[you]`
- **A demo or launch that went wrong** `[you]`
- **Learned an unfamiliar system fast** — candidate: Go for the billing work after a mostly-frontend history
  (`capella-go-training/` exists as your C#-to-Go curriculum) `[you: confirm]`

DevRev's JD weights customer-facing work. If you have no real customer-facing story, say so and use story 1 (you
owned the customer-visible behaviour) rather than inventing one.
