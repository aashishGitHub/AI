# Module 12 in simple English — Prompt versioning & the agent lifecycle

> **Read this first**
> - This is the plain-English companion to [the full guide](../12-prompt-versioning-and-agent-lifecycle.md). Read this, then the 🟢 answers there, then 🟡, then 🔴.
> - Everything here is my own lab code (lane [L]). It is a small tool I built, not a product, and it is not wired into the agent's normal run.
> - Every number comes from one small model and 5 runs per case. Treat the numbers as a seed, not a result.

## Phase 1 — Versioned prompts: files, an index and a history

**The idea.** A prompt is text that tells the model how to behave. Change one sentence and the behaviour can change.

**So we version it.** Each wording gets a number, like v1 and v2. It also gets a hash, an author and a short note.

**What is a hash?** A hash is a fingerprint of the text. Change one letter and the fingerprint changes completely.

**Where it lives.** Each prompt has a folder. The text is in files like `v1.md`. A small `index.json` file lists the versions.

**The history.** A file called `history.jsonl` records events in order. Events are only added, never rewritten. "Append-only" means that.

**The starting point.** I copied the old hard-coded prompt into v1, letter for letter. A test fails if the two ever differ.

**The first version goes live at once.** If a prompt has no production version yet, the first one added becomes production.

**The catch.** Files are simple, but two people changing them at the same time could overwrite each other. I did not test that.

**Analogy.** Think of a recipe book where every edit is a new numbered page. Nobody tears out the old page.

| Words you'll hear | Meaning |
|---|---|
| Prompt | The instruction text the model reads before it answers. |
| Version | One fixed wording of a prompt, with a number. |
| Hash (sha256) | A fingerprint of the exact text. |
| Index | The small file listing versions and which one is live. |
| Alias | A label such as production or canary that points at a version. |
| Production | The version real runs use by default. |
| Append-only | You can add new lines, but you never change old ones. |

**Say it in one breath:** Each prompt is a numbered, hashed file with a history, so I can go back.

## Phase 2 — Immutability and tamper detection

**The idea.** "Immutable" means it never changes after it is created. Version 3 stays version 3 forever.

**How do you fix a typo, then?** You add version 4. You do not edit version 3.

**Why bother?** The history stays honest. And a test result stays tied to the exact words that were tested.

**Rule on writing.** The code opens the file in "create only" mode. If the file already exists, it refuses. It even refuses a stray file the index does not know about.

**Rule on reading.** Every read recomputes the fingerprint. If it does not match the saved one, the code raises an error called `TamperError`.

**Where that check applies.** Running a prompt, promoting it and rolling back to it all read the file. So an edited file cannot slip through any of them.

**Name safety.** A prompt name becomes a folder name. So names with slashes or dots are refused. That stops writing outside the store.

**How strong is it?** It catches careless edits. It is not a security lock. The fingerprint sits next to the file, so someone could edit both.

**What it costs.** A tampered prompt stops the agent instead of running unreviewed text. That is safe, but it is also an outage.

**Analogy.** Think of a tamper seal on a medicine bottle. A broken seal tells you something changed. It does not stop a determined thief.

| Words you'll hear | Meaning |
|---|---|
| Immutable | Cannot be changed once created. |
| Tamper | Change something it should not have changed. |
| Fail closed | When unsure, stop instead of carrying on. |
| Exclusive create | Open a file only if it does not exist yet. |
| Orphan file | A file on disk that the index does not list. |

**Say it in one breath:** A version is written once and checked on every read, so quiet edits fail.

## Phase 3 — Pinning, resolution order and rollback

**The idea.** "Resolve" means: pick which version a run gets. One function does this, and the order is fixed.

**The order.** First, a version named in the call. Second, a pin. Third, the canary, if the run falls in its share. Last, production.

**What is a pin?** A pin forces every run onto one version until someone clears it. Use it to freeze behaviour during an incident.

**What a pin does not do.** It does not change which version is production. It only overrides what runs receive.

**The reason string.** Resolve also returns a short reason, like "pinned to 2". That reason later goes into the log.

**Rollback.** Rollback moves production back to the version it replaced. It works by replaying the history as a stack of production versions.

**Why not just subtract one?** Versions are not always promoted in order. The history knows what really happened.

**Safety checks.** Rollback refuses if the history and the index disagree. It also refuses to go back to a tampered version.

**Common trap.** Rollback changes only production. It does not clear a canary or a pin. A bad canary needs the canary cleared.

**Another trap.** A forgotten pin hides later promotions. The list command shows the pin, which is your only warning.

**Analogy.** Think of a thermostat with a manual override. The override beats the schedule until you switch it off.

| Words you'll hear | Meaning |
|---|---|
| Resolve | Decide which version a run gets. |
| Pin | Force one version for all runs. |
| Run key | An id for a run, used to pick its share. |
| Rollback | Move production back to the earlier version. |
| Stack | A list where you add and remove at the end. |

**Say it in one breath:** Resolve checks explicit, pin, canary, then production; rollback replays history.

## Phase 4 — Canary and shadow (bucketing)

**The idea.** A canary sends a small share of runs to the new version first. If it is bad, few runs suffer.

**Shadow mode.** Shadow runs the new version beside the old one but hides its answer. Nobody sees it, so there is no user risk.

**What I built.** The canary works. Shadow is half built: the code can name the pair, but nothing runs the second one.

**How the share is chosen.** The code hashes the prompt name and the run key together. It turns the start of the hash into a number from 0 to 99. That number is the bucket.

**The rule.** If the bucket is below the canary percent, the run gets the canary. Otherwise it gets production.

**Why this design?** The same run key always gets the same version. No random dice, so results are repeatable.

**Edge case.** At 10 percent, bucket 9 gets the canary. Bucket 10 does not. A test checks this.

**Ramping up.** Raising the percent only adds keys. A key that was already on the canary stays there.

**What is missing.** Setting a canary has no eval gate. It checks only that the percent is 0 to 100 and the version exists. Nothing watches the canary or rolls it back.

**Small samples are weak.** Zero failures in 5 canary runs still allows a true failure rate near 43 percent.

**Analogy.** Think of a restaurant trying a new dish on every tenth table. Shadow is cooking it in the kitchen but not serving it.

| Words you'll hear | Meaning |
|---|---|
| Canary | A small share of traffic on the new version. |
| Shadow | Run the new version too, but hide its answer. |
| Bucket | A number from 0 to 99 made from a hash. |
| Deterministic | Same input always gives the same result. |
| Sticky | A user keeps getting the same version. |

**Say it in one breath:** A hash gives each run a bucket; low buckets get the candidate.

## Phase 5 — Eval-gated promotion

**The idea.** A gate is a rule that must pass before a prompt becomes production.

**What goes in.** Two eval reports: one for the candidate, one for current production. An eval report lists test cases with passes and runs.

**What makes it refuse.** Any safety failure in the candidate. A different model. Different test cases. Too few runs. A case that is credibly worse.

**What is "credibly worse"?** The gate uses a Wilson interval, a range for a pass rate that stays sensible with few runs. It refuses only if the candidate's upper bound is below the baseline rate minus a margin.

**So a small dip is fine.** 9 out of 10 against 10 out of 10 is tolerated. 5 out of 10 is refused, and the reason shows the arithmetic.

**What the gate does not do.** It does not prove the candidate is better. It only says "not credibly worse".

**What it writes.** An approval moves production and records the report hashes and the gate settings. A refusal records every reason. A dry run records nothing.

**Report stamps.** A report can carry the prompt name, version and hash. The gate checks the stamp matches. An unstamped report only gets a warning.

**My real result.** I ran the gate as a dry run on my v1 and v2 evidence. It refused, because each case had 5 runs and the minimum is 10.

**With the minimum lowered to 5.** The dry run approved. v2 was higher on two cases and equal on four. I did not promote anything.

**A different check.** A separate script checks that the eval prompt carries every rule of the server's prompt. It guards the RAG eval, not this registry.

**Analogy.** Think of a driving test. Passing means you are not dangerous. It does not mean you are the best driver.

| Words you'll hear | Meaning |
|---|---|
| Gate | A rule that must pass before a change goes live. |
| Promote | Make a version the production one. |
| Baseline | The current production version, used for comparison. |
| Candidate | The new version being tested. |
| Margin | How much worse is tolerated. |
| Dry run | Show the decision but change nothing. |
| Safety failure | A run where the agent did something it must never do. |

**Say it in one breath:** Production moves only if reports are comparable, safe and not credibly worse.

## Phase 6 — Provenance: which prompt produced this answer

**The idea.** Provenance means being able to say where something came from. Here: which exact prompt made this answer.

**What to record.** The prompt name, the version, the hash and the reason it was chosen.

**Why the hash too?** A version number can be mistaken. The hash identifies the exact text.

**How.** One small function writes a "prompt resolved" line to the audit log before the run starts. A test checks the logged hash matches what the model really received.

**More records.** Each promotion in the history stores the hashes of both reports. The live comparison stamps each report with the prompt it used.

**The honest gap.** The normal agent run does not call that function. It still uses the hard-coded prompt. Only tests call it.

**So can I answer "which prompt last Tuesday"?** Not automatically. I could rebuild it by hand from the audit log, the history timestamps and the code's git history.

**The next step.** The orchestrator already has a hook to supply prompts. It returns only text, so it cannot carry the version or hash yet.

**Analogy.** Think of a label on a food package with the batch number. Without the label, a recall is guesswork.

| Words you'll hear | Meaning |
|---|---|
| Provenance | The record of where something came from. |
| Audit log | A line-by-line record of what a run did. |
| Stamp | Name, version and hash written into a report. |
| Wired | Actually connected into the real code path. |
| Hook (seam) | A place where you can plug something in. |

**Say it in one breath:** A run can log its prompt, but my normal agent path does not yet.

## Phase 7 — Honest comparison: live runs and Wilson intervals

**The idea.** To compare two prompts fairly, use the same cases, the same model and the same number of runs.

**Show the counts.** Say "5 of 5", not "100 percent". Add a range for how unsure you are.

**The range I use.** A 95 percent Wilson interval. It says where the true pass rate could plausibly be.

**Why it matters.** 5 of 5 gives a lower bound of about 0.57. 50 of 50 gives about 0.93. Same rate, very different certainty.

**How the comparison runs.** I name the prompt and versions. The tool runs each version against the cases on a local model. It writes one report per version and prints a table.

**A small trick.** The eval code has no place for a system prompt. So I swap one function in for the duration of the run, then put it back. A test checks that.

**What my files show.** Both are 5 runs per case, one small model, six cases. Neither had safety failures.

**The numbers.** On one case v2 passed 5 of 5 and v1 passed 1 of 5. On another v2 passed 5 of 5 and v1 passed 0 of 5. The other four cases were equal.

**Only one of those pairs is clearly apart.** The 0 of 5 against 5 of 5 pair does not overlap. The 1 of 5 against 5 of 5 pair does overlap.

**What v2 did not fix.** The case v2 was written to fix is still 0 of 5. So I did not fix the failure I aimed at.

**Why be careful.** Runs at temperature 0 are probably near-copies of one run. Some failures are network errors. The report keeps a set of reasons, not a count.

**Do not quote 0.2 versus 0.5.** That pools very different cases. It is not a fair "30 point gain".

**Analogy.** Think of asking five friends which film is better. Five votes is a hint, not a verdict.

| Words you'll hear | Meaning |
|---|---|
| Wilson interval | A range for a pass rate that works with few runs. |
| n | How many runs per case. |
| Held-out case | A test case written before you looked at results. |
| Temperature | A setting for how random the model is. 0 means least random. |
| Pooled | Mixed together across different cases. |
| Overlap | The two ranges share some values, so you cannot tell them apart. |

**Say it in one breath:** I compare with counts and intervals, and n=5 on one model is only a hint.

## Mix-ups to avoid

- **Pin is not rollback.** A pin overrides what runs get. Rollback moves the production label. A rollback does not clear a canary.
- **Canary is not shadow.** A canary shows real users the new version. Shadow hides it. Only the canary is built.
- **Approved is not better.** The gate approves "not credibly worse". It never proves improvement.
- **The hash is not security.** It detects careless edits. It does not stop someone who edits file and index together.
- **Built is not wired.** The provenance function exists and is tested. The normal agent run does not call it.
- **5 of 5 is not 100 percent sure.** With 5 runs, the true rate could still be about 57 percent.
- **My two tables disagree.** The notes file and the evidence files give different baselines for one case. I do not mix them.

## What I built vs what I only know

| I built and tested (lane [L]) | I only know, or have not built |
|---|---|
| Numbered, hashed, immutable prompt versions with an index and an append-only history. | Hosted prompt-management products. I did not use any, so I do not compare. [K] |
| Resolution order: explicit, pin, canary, production. | Choosing a run key for real traffic. No real caller exists. |
| Deterministic bucketing for a canary, with tests on share and ramping. | Shadow execution and comparing shadow answers. Not built. |
| An eval gate with Wilson intervals, and rollback from history. | Automatic canary monitoring or rollback. Not built. |
| A provenance log function and report stamps. | Wiring provenance into the normal agent run. Not done. |
| A live comparison command and two n=5 evidence files on one small model. | Whether v2 is really better. Needs more runs, more cases and another model. |
| 86 tests for the registry, all passing on my machine. | Safe use by two writers at once. Not tested. |
