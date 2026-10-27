# Module 12 scenarios — Prompt versioning & the agent lifecycle

> Six real-time situations, laddered 🟢 to 🔴, built on the registry in `AI/agent-lab/promptreg/` and the guide [12-prompt-versioning-and-agent-lifecycle.md](../12-prompt-versioning-and-agent-lifecycle.md). Each scenario follows one template: situation, level, what is tested, questions to ask first, control and data flow, diagnosis, fix now versus fix properly, how to test it, a 60 to 90 second spoken answer, follow-ups, and a tie to my own code with a lane tag. All code is lane [L]. The registry is a lab tool that is not wired into the agent's default run, so every "in production" situation below is a situation I reason about from the code, and I say so in each answer. Commands run from the `agent-lab` directory; I give them one per line for you to run.

| # | Level | Situation | Core idea tested |
|---|---|---|---|
| 1 | 🟢 | A prompt file was edited in place and the agent starts failing | Immutability, tamper detection, fail closed |
| 2 | 🟢 | A customer asks which prompt produced an answer last Tuesday | Provenance, and the honest gap |
| 3 | 🟡 | Two engineers change the same prompt at the same time | Immutable numbering, lost updates, orphan files |
| 4 | 🟡 | The gate passed on n=5, but production runs a different model | What the gate does and does not compare |
| 5 | 🔴 | A 10 percent canary shows rising safety failures | Canary control, rollback versus clear, ungated canary |
| 6 | 🔴 | Rollback while durable runs are in flight | Prompt version per run, replay divergence |

## Scenario 1 — 🟢 The prompt file was edited in place

**Situation.** Tuesday 09:40. A teammate says the agent "stopped working" after a merge. Every run that asks the registry for the `system` prompt fails with an error that says version 1 "was modified". The merge touched `prompts/system/v1.md` to fix a typo.

**Level.** 🟢 Beginner.

**What's being tested.** Whether I understand why versions are immutable, what the hash check does, and that failing closed is deliberate.

**Questions to ask first.**
1. Which command or service raised the error, and what is the full message with both hashes?
2. Was the edit intended, a typo fix, or accidental, such as a formatter?
3. Did anyone also edit `index.json`, or only the version file?
4. Is any service pinned to this version, or does everything resolve production?

**Control and data flow.**

```
caller -> registry.resolve(name, run_key)
       -> store.load_index(name)            (reads index.json: version -> sha256)
       -> store.read_version(name, 1)       (reads v1.md, recomputes sha256)
            recorded sha256 != file sha256  -> TamperError, run never starts
```

**Diagnosis steps.**
1. Reproduce and read both hashes in the message; the first one is the index, the second one is the file on disk.

```
.venv/bin/python -m promptreg show system 1
```

2. See what changed in the file, using git, not the registry; the registry's own `diff` command reads both versions, so it fails too.

```
git diff -- prompts/system/v1.md
```

3. Note that `list` prints only the index, so it looks healthy while `show` fails; do not use `list` to decide the store is fine.

```
.venv/bin/python -m promptreg list
```

**Fix now versus fix properly.**
- *Now:* if the edit was not meant, restore the file from git and the next resolve works again. If it was meant, restore the original first, so v1 is the text everyone measured.
- *Properly:* add the corrected text as the next version with `promptreg add`, run the evals, and promote it through the gate. A typo fix is a new version, v3 here, not an edit of v1.
- *Prevent:* by my reading of the seed tests, an in-place edit of v1 or v2 should also fail CI, because they resolve both versions and compare v1 with the constant in `agent/loop.py`, and `agent-eval.yml` runs that suite on pull requests that touch `agent-lab/**`. I did not demonstrate that by editing the file, so verify before an interview.

**How you'd test it.** The store-level test edits a file and expects `TamperError` from `read_version` and from `resolve`. I did not see a CLI-level test that asserts the exit code and stderr text for a tampered version, so that is a gap. A new test would edit a version file, run `main(["show", ...])`, and assert exit code 2 and the message.

**Spoken answer (60-90 s).** "First I would read the error, because it prints two hashes: the one recorded in the index and the one of the file on disk. That tells me the file changed and the index did not. The registry fails closed on purpose: a version is immutable, so if its text no longer matches its recorded hash, it refuses to serve it instead of running words nobody reviewed or measured. So the immediate fix is to restore the file from git, and the agent works again. If the edit was a real typo fix, the right route is a new version: add it with the CLI, run the evals, and promote through the gate, so the measurement stays attached to exact text. I would also tell the team that this check catches careless edits, not a determined one, because the hash sits next to the file. And I would check that CI fails on an edited version, which I believe it does through the seed tests, but I would verify that before relying on it."

**Follow-ups.**
- *Why not just update the hash in the index to match the new text?* Because then the old measurements no longer describe the text that runs, and history says something untrue. A new number keeps both honest.
- *Could someone bypass the check?* Yes, by editing the file and the index together. The backstop is code review and git, which are outside the package.
- *What does fail closed cost?* An outage until someone acts. A fallback to the last known good version would be better in production; I did not build it.

**Tie to my code. [L]** `AI/agent-lab/promptreg/store.py:92-118` (exclusive create and hash check on read), `AI/agent-lab/tests/test_promptreg_store.py:47-54` (tamper test), `AI/agent-lab/tests/test_promptreg_seed.py:9-23` (seeded store verifies clean).

## Scenario 2 — 🟢 "Which prompt produced this answer last Tuesday?"

**Situation.** Friday 11:15. A customer's engineer sends a transcript from last Tuesday where the assistant acknowledged the wrong alert. Support asks you: which prompt wording was live, and has it changed since?

**Level.** 🟢 Beginner, with a 🔴 honesty trap.

**What's being tested.** Provenance: what the system records, what it does not, and whether I admit the gap.

**Questions to ask first.**
1. Which run is it: a run id, or only a time and a tenant?
2. Which entry point made it: the single-agent CLI, the orchestrator, or an eval run?
3. Where are the audit logs kept, and for how long?
4. Was there a canary, a pin or a promotion around that time?

**Control and data flow.**

```
registry.resolve -> PromptRef(name, version, sha256, text, reason)
      |-> record_prompt_ref(audit, ref) -> audit line "prompt_resolved"
      |-> system_prompt=ref.text -> run_session / run_agent
(wired: tests and live_compare only; the CLI agent passes the SYSTEM_PROMPT constant)
```

**Diagnosis steps.**
1. Find the run's audit log and look for a `prompt_resolved` line before `run_start`. If it is there, it names the version, the hash and the reason. In my repo a normal agent run does not write one, because `record_prompt_ref` is called only from tests.
2. If there is no such line, read the registry history for events around that date: promotions, rollbacks, canary changes and pins, each with a timestamp.

```
cat prompts/system/history.jsonl
```

3. Check which text the constant had on that date, using the git history of the file that holds it.

```
git log --follow -p -- agent/loop.py
```

4. Compare the hash of the candidate text with any hash that appears in the log; a hash settles which bytes ran, a version number does not.

**Fix now versus fix properly.**
- *Now:* answer with what I can prove, and label the rest. For example: "The history shows only the bootstrap of v1 until that date, and the CLI agent used the constant that the seed test keeps byte-identical to v1, so v1 is my best answer. The log for this run has no prompt record, so I cannot prove it."
- *Properly:* wire `record_prompt_ref` into the real run path, so every run logs its prompt line; keep the logs long enough; and add a small point-in-time query that replays the history to say which version was production, canary or pinned at a timestamp. I did not build that query.

**How you'd test it.** The existing provenance tests show the audit line comes first, that its hash equals the hash of the system message the model received, and that a canary run logs its bucket. A new test would drive the real CLI path and assert that the audit log contains one `prompt_resolved` line. That test does not exist because the path is not wired.

**Spoken answer (60-90 s).** "I would answer with what I can prove and say clearly what I cannot. My registry can record the prompt name, version, hash and the reason it was chosen as one line in the audit log. But in my lab that function is called only from tests; the normal agent run uses a constant, so it writes no such line. So for last Tuesday I would reconstruct it: read the registry history for promotions, rollbacks, canary and pin events around that date, then check the git history of the file with the constant. In my seeded store the history has only the first version, and a test keeps that version byte-identical to the constant, so I could say version 1 is my best evidence, but I would not say it is proven for that run. The fix is to wire the provenance call into every run and keep the logs, and I would add a point-in-time query over the history. I have not built that part."

**Follow-ups.**
- *Why log the hash as well as the version?* A number can be wrong or reused; the hash identifies the bytes.
- *Can history alone answer it?* It tells me which version was meant to be live, not which one a given run actually received, because a pin, a canary or an explicit version overrides production.
- *Whose clock is in the timestamps?* The system clock, unless a test injects one. I would verify clock behaviour across machines before trusting an ordering.

**Tie to my code. [L]** `AI/agent-lab/promptreg/provenance.py:7-8`, `AI/agent-lab/tests/test_promptreg_provenance.py:23-71`, `AI/agent-lab/agent/loop.py:37-45` (the constant is the default), `AI/agent-lab/prompts/system/history.jsonl:1`.

## Scenario 3 — 🟡 Two engineers change the same prompt at the same time

**Situation.** Wednesday 15:30. Priya and Sam both ran `promptreg add system --file ...` within seconds of each other. Priya's succeeded. Sam's printed an error saying a version "already exists" and is immutable. Sam is now trying to force it.

**Level.** 🟡 Intermediate.

**What's being tested.** Where my design is safe under concurrency, where it is not, and what a stuck state looks like.

**Questions to ask first.**
1. What exactly did Sam's error say: exists in the index, or exists on disk?
2. Are they on one machine and one directory, or on two branches in git?
3. Did either of them also change the canary, the pin or production in the same minute?
4. Is any file in the prompt folder not listed in `index.json`?

**Control and data flow.**

```
add_version(name, text):
  index   = load_index()                    # both engineers read: max version = 2
  number  = max(index.versions) + 1         # both compute 3
  open("v3.md", "xb")                       # exclusive create: exactly one wins
     winner: writes file, saves index
     loser : FileExistsError -> VersionExists("already exists ... immutable")
```

**Diagnosis steps.**
1. Confirm the winner's state.

```
.venv/bin/python -m promptreg list
```

2. See both texts, and decide which one is wanted, or whether both are.

```
.venv/bin/python -m promptreg show system 3
```

3. Look for an orphan: a `v<N>.md` file that exists on disk but not in the index. If one engineer's process died between writing the file and saving the index, the file is there and the index is not.
4. Read the history to see whether alias changes from the two engineers were both recorded.

```
cat prompts/system/history.jsonl
```

**Fix now versus fix properly.**
- *Now:* Sam does not force anything. Sam runs `add` again; the number is recomputed from the index and becomes 4, so both texts are kept. Then both go through the gate on their own merits.
- *Orphan case:* by my reading, the number is always computed from the index, and the CLI has no version option, so an orphan file at the next number refuses every add until someone removes it or calls the Python API with an explicit number. A test shows the refusal; I did not test the recovery.
- *Properly:* adding a version is safe, because exclusive create is the lock, but changing aliases is a read-modify-write of `index.json` with no lock. By my reading, two simultaneous canary or promote commands can lose one update, and I did not test that. A shared store would need a compare-and-set on the index.

**How you'd test it.** Fire two `add_version` calls at once from two threads or processes and assert that one number is taken twice at most once: exactly one winner per number and the loser gets `VersionExists`. For aliases, a test that interleaves two `set_canary` calls would show the lost update; that test does not exist, and I would expect it to fail today.

**Spoken answer (60-90 s).** "For adding versions the design holds up: the version file is opened in exclusive-create mode, so when two people compute the same next number, exactly one wins and the other gets an error that the version exists. Sam should not force it. Sam reruns the add, gets the next number, and both texts are kept, each of which then has to pass the eval gate separately. What I would worry about is different: changing aliases like the canary or production is a read-modify-write of one JSON file with no lock, so two simultaneous changes can overwrite each other. I have not tested that, so I would say it is a known gap. I would also check for an orphan file left by a crashed add, because by my reading it blocks every later add until someone removes it. A shared deployment would need a compare-and-set on the index."

**Follow-ups.**
- *Why not a lock file?* A lock file adds staleness and cleanup problems; exclusive create already gives atomic numbering. The alias update needs real compare-and-set, which a lock file only approximates.
- *What if they were on two git branches?* Both branches add a v3 file and change `index.json`, so git reports a conflict. A human renumbers, and the index hash must still match the file, so the safe route is to re-add through the tool.
- *Is `os.replace` enough?* It gives an atomic swap of the file on one filesystem, I believe; verify in the docs. It does not stop two writers each swapping in their own version.

**Tie to my code. [L]** `AI/agent-lab/promptreg/store.py:85-108`, `AI/agent-lab/tests/test_promptreg_store.py:38-44` (orphan refused), `AI/agent-lab/promptreg/registry.py:63-89` (alias changes).

## Scenario 4 — 🟡 The gate passed on n=5, but production runs a different model

**Situation.** Thursday 16:00. After a promotion, answer quality drops in production. The release notes say the gate approved. The team lead asks how a gate that "needs evidence" let this through. Production uses a larger model than the one the evals used.

**Level.** 🟡 Intermediate.

**What's being tested.** Whether I know exactly what the gate compares, what it records, and where its blind spots are.

**Questions to ask first.**
1. What were the gate settings in the `promote` history event, and was the minimum number of runs lowered?
2. What `model` and `n` do the two report files say?
3. Is the production model recorded anywhere in the registry?
4. Do the reports carry a prompt stamp, or were they accepted with a warning?

**Control and data flow.**

```
promote(name, v, candidate.json, baseline.json, gate)
  evaluate(): safety_failures(candidate) == 0 ?
              candidate.model == baseline.model ?          (both from the report files)
              same case ids ? runs >= min_runs ? not credibly worse ?
  registry  : stamp(report) == (name, version, sha256) ?   (missing stamp = warning only)
  approved  -> production = v ; history "promote" + report hashes + gate settings
(production model never enters this flow)
```

**Diagnosis steps.**
1. Read the last history event; it records both report hashes and the gate settings used.

```
cat prompts/system/history.jsonl
```

2. Open the two report files that the hashes name and read `model`, `n` and the `prompt` stamp.
3. Check how many runs each case had. At the defaults a case with fewer than 10 runs refuses, so an approval at n=5 means the minimum was lowered. On my own evidence files, the dry run at the defaults gave 12 refusal reasons, and at `--min-runs 5` it approved.

```
.venv/bin/python -m promptreg promote system 2 --candidate prompts/system/evidence/system-v2-n5.json --baseline prompts/system/evidence/system-v1-n5.json --dry-run
```

4. Compare the evaluation model with the production model by hand, since the gate cannot.

**Fix now versus fix properly.**
- *Now:* roll production back to the previous version, then check that no canary or pin is hiding the change.

```
.venv/bin/python -m promptreg rollback system
```

- *Properly:* the gate only checks that the candidate report and the baseline report agree with each other on `model`. Neither says anything about production. By my reading, if both reports lack a `model` field the comparison sees two empty values as equal, so unlabeled reports pass; I did not test that, so verify it. I would record the target model in the report and in the registry, make the gate refuse a report whose model differs from the production target, fix the gate settings in reviewed configuration so the person promoting cannot lower them, raise n, use held-out cases, and run at a temperature above zero so runs are real samples.

**How you'd test it.** The existing test already refuses a candidate report with a different model than the baseline. New tests: a report with no model must be refused or warned; a report whose model differs from the registered production model must be refused; and the `promote` event must show the gate settings, which an existing test already asserts.

**Spoken answer (60-90 s).** "I would start from what the gate actually compares. It checks that the candidate and baseline reports agree on model, case set and run counts, that there are no safety failures, and that no case is credibly worse. It never sees the production model. So if production runs a different model than the evals, the gate cannot notice. Second, at its defaults it refuses fewer than ten runs per case. On my own n=5 evidence it refuses, so an approval at n=5 means someone lowered the minimum, and the history records the settings used, so I can see who did. My immediate step is to roll production back and check there is no canary or pin masking it. The proper fix is to record the target model, make the gate compare against it, fix the gate settings in reviewed config, and increase n and the case set. I would also say an approval only means not credibly worse, never better."

**Follow-ups.**
- *What does "not credibly worse" mean in numbers?* The Wilson upper bound of the candidate must not fall below the baseline rate minus 0.05. With n=10, 9 of 10 against 10 of 10 is tolerated and 5 of 10 is refused.
- *Why is n=5 weak?* 5 of 5 still allows a true pass rate down to about 0.57 at 95 percent, and at temperature 0 the five runs may be near-copies of one run.
- *Should a refused promotion be forceable?* Not by the person who wants it. I did not build an override or an approver identity.

**Tie to my code. [L]** `AI/agent-lab/promptreg/gate.py:66-105`, `AI/agent-lab/promptreg/registry.py:91-127`, `AI/agent-lab/tests/test_promptreg_gate.py:84-87` (different model refused), `AI/agent-lab/prompts/system/evidence/system-v2-n5.json:1-17`.

## Scenario 5 — 🔴 A 10 percent canary shows rising safety failures

**Situation.** Monday 11:20. Prompt v2 has been a 10 percent canary since the morning. An on-call engineer sees more runs trying a write the user did not ask for. Nobody has promoted v2. Do you roll back?

**Level.** 🔴 Senior.

**What's being tested.** Whether I use the right control (clear the canary, not rollback), what I can and cannot measure per version, and whether I admit that a canary in my lab is ungated and unwatched.

**Questions to ask first.**
1. Is the increase only in canary runs, or across all runs? Can I split by version?
2. What counts as a safety failure here, and did a write actually execute, or was it only attempted and denied?
3. How many runs is this: 3 of 40, or 300 of 4,000?
4. Was v2 measured before the canary? Which cases, which model, what n?
5. Is production still v1, and is any pin set?

**Control and data flow.**

```
run starts -> resolve(name, run_key)
   bucket = sha256(name:run_key)[:8] as int % 100
   bucket < 10 -> v2 (reason "canary: bucket b < 10")   else -> v1 (reason "production: ...")
   |-> record_prompt_ref -> audit "prompt_resolved"   (only if wired)
write tool -> ApprovalGate (code, default deny) -> executes only with a recorded approval
```

**Diagnosis steps.**
1. Stop the bleeding first, then investigate. Clearing the canary stops new runs from resolving v2; runs already started keep the text they resolved.

```
.venv/bin/python -m promptreg canary system --clear
```

2. Confirm state: canary empty, production v1, no pin.

```
.venv/bin/python -m promptreg list
```

3. Split the audit logs by the `version` in `prompt_resolved`. That works only for runs that logged it; in my repo the default path does not, so this is the first thing I would check and possibly the first gap.
4. Read what changed in the wording, sentence by sentence.

```
.venv/bin/python -m promptreg diff system 1 2
```

5. Reproduce on the failing cases for both versions, same model, with intervals, using the live comparison. Treat a handful of runs as a hint, not a verdict.

**Fix now versus fix properly.**
- *Now:* clear the canary. Do not call `rollback`: production never moved, and by my reading rollback does not touch the canary, so it would either fail for lack of an earlier production or move production for no reason.
- *Keep the evidence:* v2 stays as an immutable file; its failing runs become eval cases.
- *Properly:* in my lab, `set_canary` checks only the percent range and that the version exists, so an unmeasured version can be canaried, while `promote` demands zero safety failures. I would require measured evidence before a canary, add an automatic stop on any safety failure, split metrics by version, and ramp in steps. None of that is built.
- *Bound the damage regardless of wording:* the approval gate is code that denies writes by default, so a worse prompt raises the rate of attempts, but an unapproved write still does not run. That is the layer that does not depend on the model.

**How you'd test it.** Existing tests show the share stays within 1.5 points of the percentage, that the boundary bucket stays on production, and that ramping only adds keys. New tests: `set_canary` refuses a version without evidence; a safety-failure counter above zero clears the canary; and an end-to-end test where a canary run's audit line carries its version and bucket. Only the last is close to an existing test.

**Spoken answer (60-90 s).** "First I stop the exposure: I clear the canary, so new runs resolve production. Runs in flight keep the text they already got. I would not roll back, because production never changed, and rollback moves only the production alias, so it does not touch the canary. Second, I check what the damage can be. Writes need an approval that is enforced in code, so a worse prompt can raise attempts, but an unapproved write does not execute. Third, I investigate: split the logs by prompt version, which only works if the prompt line is logged, and in my lab that is not wired by default, so that is a gap I would name. Then I diff the wording and reproduce on the failing cases with intervals. Longer term I would gate the canary itself, because in my lab it only checks the percent and that the version exists, add an automatic stop on any safety failure, and ramp in steps."

**Follow-ups.**
- *Is 3 failures in 40 canary runs enough to act?* For a safety counter with zero tolerance, yes, act; for a task metric, judge with an interval. By Wilson symmetry, even zero failures in 5 runs allows a true rate near 43 percent.
- *How would you pick the run key?* A conversation id, so one conversation does not flip between versions. No production caller exists in my repo, so this is a design choice.
- *Would shadow mode have caught it?* Possibly, with no user risk, but shadow is half built: `resolve_shadow` returns the pair and nothing runs the second one.

**Tie to my code. [L]** `AI/agent-lab/promptreg/registry.py:35-48` (resolve), `:63-76` (set and clear canary), `AI/agent-lab/promptreg/bucketing.py:6-8`, `AI/agent-lab/tests/test_promptreg_resolution.py:34-39` and `:116-131`, `AI/agent-lab/agent/approval.py:34-47` (the gate that bounds the damage). The v2 prompt in the repo was never canaried: its index shows no canary and the history has only the bootstrap event.

## Scenario 6 — 🔴 Rollback while durable runs are in flight

**Situation.** Friday 14:05. Prompt v3 was promoted at 14:00 and is clearly bad. You run the rollback at 14:05. At that moment the orchestrator has runs paused in `waiting_approval`, and a worker crashed and will resume another run in a minute. A colleague asks: what prompt does each of those runs use now?

**Level.** 🔴 Senior.

**What's being tested.** Whether I see that "which version" is a per-step lookup unless I store it per run, and what a mixed-version run does to replay and approval.

**Questions to ask first.**
1. How does the orchestrator get its prompts: the role strings, or a provider backed by the registry? In my repo it is only the role strings or a test lambda.
2. When is the prompt looked up: once at run start, or on every step attempt?
3. Which runs have already journaled or approved a write?
4. Can in-flight runs be cancelled and restarted safely, and which of them have written anything?

**Control and data flow.**

```
engine._attempt(role, step, attempt)
   o.system_prompt(role) -> prompt_provider(role.name)      # looked up on every attempt
resume after crash or after approval -> the step runs again -> the lookup runs again
   registry.resolve(...) between boots may now return v2 instead of v3
journal: the approved write call at index i is replayed only if the model asks for the same call again
```

**Diagnosis steps.**
1. List the runs and their steps and statuses with the existing status command of the orchestrator CLI; verify its exact name and flags in the module 11 guide before running it.
2. For each run, note which steps already succeeded (their output is stored and will not run again) and which are still to run.
3. For each run waiting for approval, read the pending call that a human is being asked to approve.
4. Find out which prompt text each completed step used. If nothing recorded it, that is the gap.

**Fix now versus fix properly.**
- *Now:* stop new exposure with the rollback so new runs resolve the previous production. For paused runs, I would rather end them and restart than let a human approve a call produced under a prompt I now distrust; the orchestrator can cancel a run. Runs that have already executed a write need a human look first.
- *Why not let them resume:* a run that continues after the rollback would produce its early steps under one prompt and its later steps under another. By my reading of the journal, a model that sees a different prompt after an approval may ask for a different write at the same call index, and the journal then fails the step as "replay diverged". The failure is safe, since the write does not run, but the run dies.
- *Properly:* resolve once when the run starts and store the reference, name, version and hash, with the run, so every step and every resume gets the same text. The provider seam returns only text today, so it would change to return the reference, and the run row would gain a field. That is a design, not built; the registry is not imported anywhere in the orchestrator.

**How you'd test it.** Extend the crash-matrix style from module 11: boot one orchestrator with a registry-backed provider on v3, crash after the first step, change production to v2, boot a second one and resume. Assert that every step's system message in that run shows the same hash. Today that test would fail, which is the point.

**Spoken answer (60-90 s).** "The honest answer is that in my code the registry is not connected to the orchestrator, so I would say what would happen if it were. The orchestrator looks up the prompt for every step attempt, through a provider that returns text. If that provider called resolve, then a run that resumed after the rollback would get the old version for its later steps, so one run would mix two prompts. For paused runs that is worse: after an approval the step runs again, and a model under a different prompt may ask for a different write, which the journal treats as a replay divergence and fails the step. It fails safe, but the run dies. So I would stop new exposure with the rollback, cancel and restart the paused runs, and have someone look at any run that already wrote. The proper fix is to resolve once at run start and store the name, version and hash with the run. I would prove it with a crash test that changes production between two boots and checks every step saw the same hash."

**Follow-ups.**
- *Why not pin the bad version until runs finish?* A pin is global per prompt name, so it would also keep new runs on the bad prompt.
- *Would a reference stored per run cost anything?* A field on the run row and a lookup by hash instead of by alias. The text must stay available, which the immutable store guarantees.
- *Does the same issue exist for tool descriptions?* Yes, in principle, since they also steer the model; I did not version them.

**Tie to my code. [L]** `AI/agent-lab/orchestrator/engine.py:139-140` and `:220-242` (provider and per-attempt lookup), `AI/agent-lab/tests/test_orchestrator_engine.py:286-303` (a provider replaces the role prompts), `AI/agent-lab/orchestrator/journal.py:27-49` (replay divergence), `AI/agent-lab/promptreg/registry.py:129-147` (rollback), and module 11 for the crash matrix. The integration between registry and orchestrator is design only.
