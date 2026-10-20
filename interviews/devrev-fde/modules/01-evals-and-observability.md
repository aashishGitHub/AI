# Module 01 — Evals & observability

> This module is about proving an LLM feature works, keeping it working, and reporting honestly when it does not. The code lives in `AI/evals/` (a promptfoo RAG suite with a CI gate), `AI/agent-lab/evals/` (a trajectory eval harness for a tool-calling agent), and `AI/fe-hands-on/server/stream.go` (the grounded prompt and the request logging). Everything I measured is **[L]**, my own lab build on local Ollama models, and none of it shipped to customers. The **[P]** lane is the Couchbase Ask AI system: its shipped eval is a manually triggered script that scores answers with cosine similarity plus a GPT-4 classifier in a Google Sheet, and it has a thumbs-up/down feedback store, tiered rate limits and a troubleshooting runbook, all per the Ask AI design document as summarised in `AI/docs/notes/ai-lifecycle-business-cases.md`. Keep the lanes separate out loud: "in production we did X, in my own build I went further and did Y".

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. Define quality and the golden dataset | Turn "looks good" into a fixed set of inputs with checkable expectations, including cases that must fail. | `AI/evals/promptfooconfig.yaml`, `AI/agent-lab/evals/cases/` |
| 2. Deterministic checks first | Catch known-bad and known-required outputs with free, repeatable rules before spending a judge call. | `AI/evals/promptfooconfig.yaml`, `AI/agent-lab/evals/scoring.py` |
| 3. LLM-as-judge and calibrating the judge | Grade what rules cannot express, and prove the judge itself is right before it gates anything. | `AI/evals/promptfooconfig.yaml` |
| 4. The CI regression gate | Run the cheap tier on every PR and the model tier behind it, so eval prompt drift or a regression is a red check. | `AI/evals/ci/check-parity.py`, `AI/.github/workflows/eval-gate.yml` |
| 5. Agent and trajectory evals | Grade which tools were called, with which arguments, and what actually changed, not just the final text. | `AI/agent-lab/evals/`, `AI/agent-lab/tests/test_harness_catches_failures.py` |
| 6. Online evaluation, observability, drift, cost and latency | Watch real traffic after deploy, because offline sets only cover what I imagined. | `AI/fe-hands-on/server/stream.go`, `AI/agent-lab/agent/loop.py` |
| 7. Debugging failures and honest reporting | Read the failure reason, isolate one variable, and report live runs, held-out cases and negative results without inflating them. | `AI/agent-lab/NOTES.md`, `AI/evals/promptfooconfig.yaml` |

## Phase 1 — Define quality and the golden dataset

### 🟢 Beginner

**Q:** What is a golden dataset, and why do you need one before you change a prompt?

**A:** A golden dataset is a fixed set of inputs where each one has an expectation I can check automatically, and I rerun it on every change. Without it, "it looks good" really means "it worked on the ten prompts I happened to try". In my promptfoo suite each row is a question, a context document, one or more assertions, and tags. Right now that suite has exactly two rows, a happy path and an unanswerable question, so I describe it as a seed and not as a benchmark.

**Q:** How do you define "quality" for a documentation-assistant answer?

**A:** I split it into things I can name and check. The answer must be grounded, meaning it only uses the supplied context. When the context does not contain the answer, the right behaviour is to decline instead of inventing syntax. The answer should also be actionable, and in the shipped server prompt it should cite sources by number. I pick the checks from the failures I have actually seen, because a quality definition nobody can test is just an opinion.

### 🟡 Intermediate

**Q:** Walk me through one golden row and what makes a row good.

**A:** A good row has a realistic input, a pinned context, and assertions ordered cheapest first. My happy-path row asks how to create a primary index in Capella, points at a fixed context file, and its first assertion is a plain substring check. The second row asks about vector indexes against a context that only covers primary indexes, because a suite made only of happy paths can never fail for the right reason. I tag each row, for example `grounding` and `negative`, so I can slice results later.

**Source:** `AI/evals/promptfooconfig.yaml:36-42`
```yaml
  - description: "primary index creation (happy path)"
    vars:
      question: "How do I create a primary index in Capella?"
      context: file://golden/contexts/primary-index.md
    assert:
      - type: contains # deterministic, runs first, cheap
        value: "CREATE PRIMARY INDEX"
```

**Source:** `AI/evals/promptfooconfig.yaml:78-81`
```yaml
  - description: "unanswerable from context — must decline, not invent"
    vars:
      question: "How do I create a vector index in Capella?"
      context: file://golden/contexts/primary-index.md
```

I would say: the context is a file in `golden/contexts/`, so the row is reproducible and reviewable in a PR, and the second row is deliberately unanswerable so grounding is actually exercised.

### 🔴 Senior

**Q:** How do you stop a golden set from giving you false confidence, and where does yours fall short?

**A:** I fight three problems: it does not reflect real traffic, it gets tuned against until it is contaminated, and it rots as the corpus and product change. My answer is to seed from real queries and every production incident, to keep held-out cases that were written before I measured any fix, and to version the set like code with an owner. In the agent harness I have 17 cases, 13 golden and 4 held-out, and the held-out ones were written before the fixes were measured, per `NOTES.md`. The weakness is that my two promptfoo rows and my 17 agent cases were written by me, not mined from real user logs, so they are a seed. I have not measured how well either set matches real traffic.

**Source:** `AI/agent-lab/evals/cases/16_heldout_chain_rephrased.yaml:1-17`
```yaml
id: heldout_chain_rephrased
description: >-
  Held-out for chain_list_then_explain (written before any fix was measured). Same fixture, different phrasing.
  After listing, the alert to explain is the firing root cause, not the suppressed symptom.
prompt: Tenant streamflix looks unhealthy. Which alert matters most? Explain that one.
max_steps: 5
expect:
  tools:
    sequence:
      - tool: list_active_alerts
        args: {tenantId: streamflix}
      - tool: explain_alert
        args:
          tenantId: streamflix
          alertId: alr-1001
  final_text:
    contains: [alr-1001]
```

I would say: the `description` records that this case was written before any fix was measured, which is what lets me use it later to tell a real fix from overfitting to one phrasing.

**Follow-up they will ask:** How many cases do you actually need?

**A:** I do not have a verified number, and anyone who gives you one without knowing the effect size is guessing. The planning ratios in my interview notes (roughly 40% happy path, 25% edge, 20% adversarial, 15% regression, starting at 30 to 50 cases) are planning figures I wrote, not something I measured. What I can say from my own runs is how little a small sample tells you. Using a Wilson 95% interval that I computed, a case that passes 5 of 5 is still consistent with a true pass rate as low as about 57%, and a case that fails 0 of 10 is consistent with a true rate up to about 28%. So I size the set by the decision it gates and I report the interval, not just the pass count.

**Illustrative (not from the repo):**
```python
from math import sqrt


def wilson_interval(successes: int, runs: int, z: float = 1.96) -> tuple[float, float]:
    p = successes / runs
    denom = 1 + z * z / runs
    centre = (p + z * z / (2 * runs)) / denom
    half = z * sqrt(p * (1 - p) / runs + z * z / (4 * runs * runs)) / denom
    return centre - half, centre + half
```

I would say: this is my own helper to show how wide the uncertainty is at n=5 or n=10, and I would verify the formula in a statistics reference before putting it in a report.

## Phase 2 — Deterministic checks first

### 🟢 Beginner

**Q:** What is a deterministic check, and why run it before an LLM judge?

**A:** A deterministic check is a rule with no model in it, such as "the answer contains this string", "this output parses as JSON", or "this forbidden text is absent". It costs nothing, gives the same answer every time, and cannot be fooled by fluent prose. In my first measured run the judge used about 901 grading tokens against 278 for the answer it judged, roughly 3.2 times the generation cost. That was one case with a g-eval judge, so it is an order of magnitude and not a benchmark, but it is why a cheap rule goes first.

### 🟡 Intermediate

**Q:** Show me the rules in your suite and the reason each one exists.

**A:** The first rule is a required string, `CREATE PRIMARY INDEX`, because the happy path must contain it. The second is a `not-contains` guard for a wildcard form that appeared nowhere in the context, written because the model really produced it and the judge scored it faithful. The third, on the unanswerable row, asserts that a refusal is present using a closed list of decline phrases. I did not use a "bad string is absent" check there because my first attempt did exactly that and passed while the model invented different wording.

**Source:** `AI/evals/promptfooconfig.yaml:44-50`
```yaml
      # Regression guard for an OBSERVED failure, not a hypothetical one:
      # llama3.2:1b answered `CREATE PRIMARY INDEX ON `bucket_name`.*` — a
      # wildcard form that appears nowhere in the context — and the g-eval
      # judge scored it 1/1 "faithful". A cheap string rule catches the exact
      # bug the expensive judge missed. This is what a regression test is.
      - type: not-contains
        value: "`.*`"
```

**Source:** `AI/evals/promptfooconfig.yaml:91-100`
```yaml
      - type: icontains-any
        value:
          - "does not cover"
          - "does not contain"
          - "not covered"
          - "no information"
          - "not mentioned"
          - "cannot answer"
          - "don't know"
          - "does not provide"
```

I would say: there are few ways to decline and infinite ways to hallucinate, so I match the small set. A regression guard is a cheap rule pinned to a failure I actually observed.

### 🔴 Senior

**Q:** What do deterministic checks miss, and how did you avoid grading the agent's words instead of what happened?

**A:** The trade-off is that rules are exact but brittle, so a refusal phrased outside my eight listed phrases would be a false failure, and a rule can never judge "is this faithful". The failure mode is the opposite one for agents: if I only check the final text, a model can say "done, alert acknowledged" without calling the tool. So in the agent harness the outcome is read from the server's state file, not from the model's claim, and safety is derived from the tool records. I have a test where the model claims an action that never happened, and it fails on both the missing tool call and the state check. The boundary is that this proves the scorer is not fooled by words, and it says nothing about how often a real model makes that claim.

**Source:** `AI/agent-lab/evals/scoring.py:68-81`
```python
def _outcome(case: Case, run: RunResult, state: dict[str, Any]) -> list[str]:
    failures = []
    acknowledged = frozenset(state.get("acknowledged", {}))
    if acknowledged != case.state.acknowledged:
        failures.append(f"acknowledged alerts {sorted(acknowledged)} but expected {sorted(case.state.acknowledged)}")
    linked = frozenset(f"{link['alertId']}:{link['issueKey']}" for link in state.get("links", []))
    if linked != case.state.linked:
        failures.append(f"linked issues {sorted(linked)} but expected {sorted(case.state.linked)}")
    text = run.final_text.lower()
    failures += [f"final text is missing '{s}'" for s in case.final_text.contains if s.lower() not in text]
    failures += [f"final text contains forbidden '{s}'" for s in case.final_text.not_contains if s.lower() in text]
    failures += [f"final text does not match /{p}/" for p in case.final_text.regex
                 if not re.search(p, run.final_text, re.IGNORECASE)]
    return failures
```

**Source:** `AI/agent-lab/tests/test_harness_catches_failures.py:148-152`
```python
def test_claiming_an_action_that_never_happened_is_caught_by_the_state_check_not_the_text(golden):
    score = evaluate(golden["ack_approved"], final_turn("Done. alr-1001 is acknowledged."))
    assert score.selection.failures == ("required tool 'acknowledge_alert' was never called",)
    assert score.outcome.failures == ("acknowledged alerts [] but expected ['alr-1001']",)
    assert not score.success
```

I would say: the scorer takes `state` as a separate argument from `run`, so the outcome is checked against the system, and the text checks are the last lines of the function, not the first.

**Follow-up they will ask:** Why not require the exact refusal string instead of a list of phrases?

**A:** The shipped and eval prompts both tell the model to reply with one exact sentence, so an exact match would be the tightest rule. I used a tolerant list because a 1B model may paraphrase, and I would rather accept a legitimate decline than fail a correct behaviour. The cost is a slightly weaker check, since any of eight phrases could also appear inside a fabricated answer. I did not measure how often `llama3.2:1b` emits the exact string versus a paraphrase, so I cannot say how much the tolerance matters.

## Phase 3 — LLM-as-judge and calibrating the judge

### 🟢 Beginner

**Q:** What is LLM-as-judge, and what is the first rule for using one?

**A:** LLM-as-judge means I ask a second model to grade an output against a rubric, which lets me score things like faithfulness that no regex can express. The first rule is to use a different model, ideally a different family, from the one under test, because a model tends to rate its own style generously. The second is to pin it, with temperature 0 and a fixed model, so a score does not move for reasons unrelated to my product. In my suite the system under test is `llama3.2:1b` and the judge is `qwen2.5:3b`.

### 🟡 Intermediate

**Q:** Show me how you configured the judge and how you phrase a rubric.

**A:** The judge is set once in `defaultTest` so every assertion shares it, with temperature 0 and JSON output forced, and the comment records why the model was swapped. The rubric is the part people get wrong. promptfoo's grader asks whether the rubric statement is true of the output, so I write the rubric as a claim about the output and not as an instruction to the judge. I also use `llm-rubric` and not `g-eval`, because g-eval extracts the judge's JSON with a pattern that does not match pretty-printed multi-line JSON, which is what Ollama's JSON mode emits.

**Source:** `AI/evals/promptfooconfig.yaml:14-30`
```yaml
      # judge — different model AND different family than the SUT (llama3.2:1b),
      # to avoid self-preference bias.
      #
      # Was qwen2.5:1.5b until 2026-09-07. Isolation test: graded a FIXED output
      # ("The provided documentation does not cover this.", no SUT variance) against
      # this exact rubric, temperature 0, 3 runs. 1.5b returned pass=false all 3
      # runs, with a reason that agrees the output has no SQL statement yet marks
      # the rubric false anyway — a deterministic, reproducible inversion, not
      # sampling noise. 3b returned pass=true all 3 runs on the identical input.
      # Swapped to 3b for that reason. Re-run the isolation test before trusting
      # any future judge swap — "bigger" is not the claim, "measured correct on
      # this rubric" is.
      id: ollama:chat:qwen2.5:3b
      config:
        temperature: 0 # deterministic grading; an unpinned judge drifts run to run
        passthrough:
          format: json # force raw JSON output, no markdown fencing
```

**Source:** `AI/evals/promptfooconfig.yaml:112-113`
```yaml
      - type: llm-rubric
        value: "The output declines to answer or states the information is unavailable, and contains no SQL statement for creating a vector index."
```

I would say: the rubric describes what the output should be and contains no instructions, and the g-eval versus llm-rubric difference is from reading promptfoo's source, so I would tell them to verify it against the current version.

### 🔴 Senior

**Q:** How did you establish that your judge could be trusted, and is that calibration?

**A:** It was isolation, not calibration, and I distinguish the two out loud. I saw two different judge failures and isolated each by holding the input fixed. First, a false pass: an instruction-style rubric made both `qwen2.5:1.5b` and `3b` score a fabricated answer correct 0 of 5, and the same claim rewritten as an assertion about the output got 5 of 5 on both, so model size was not the variable. Second, a false fail on 2026-09-07: graded against a fixed correct refusal at temperature 0 for 3 runs, the 1.5b judge returned fail every time while agreeing in its own reason that there was no SQL statement, and the 3b judge returned pass 3 of 3, so I swapped it. Real calibration would be a hand-labelled batch with a judge-versus-human agreement score, and I have not done that. The honest status is "no disagreements yet on 2 cases", not "the judge is trustworthy".

**Illustrative (not from the repo):**
```python
def cohens_kappa(human: list[bool], judge: list[bool]) -> float:
    n = len(human)
    observed = sum(h == j for h, j in zip(human, judge)) / n
    p_h, p_j = sum(human) / n, sum(judge) / n
    expected = p_h * p_j + (1 - p_h) * (1 - p_j)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)
```

I would say: this is what the missing step looks like, a hand-labelled batch scored for agreement beyond chance, and I have not run it on my data. For the sample labels I used in testing it returned about 0.58, which says nothing about my judge.

**Follow-up they will ask:** Your judge passed fabrications and then failed a correct refusal. What does that tell you?

**A:** It tells me two cases were never enough. My reading is that the first set only let the judge be wrong in one direction, because the 1B model was fabricating, so there was no correct refusal for it to grade and the inversion stayed hidden until the prompt fix made the model refuse. I am reading that ordering from the commit dates and the notes, so verify it against git history before you rely on it. The fix I would make is a labelled set with both polarities per rubric, correct declines and fabrications, and a rule that every judge or rubric change reruns the fixed-input isolation. I also pin the judge by a model tag, `qwen2.5:3b`, and I have not verified that a tag is immutable, so I would pin by digest for anything that gates.

## Phase 4 — The CI regression gate

### 🟢 Beginner

**Q:** What is a CI regression gate for an LLM feature?

**A:** It is an automated check that runs on every pull request that touches the prompt or the eval, and turns a regression into a red build instead of a surprise in production. Prompt changes are non-deterministic behaviour changes, so without a gate every prompt tweak is an unreviewed deploy. I run two tiers because they cost different amounts and mean different things. The first is a free parity check with no model, and the second runs the golden set against local Ollama models.

### 🟡 Intermediate

**Q:** Explain the parity tier and show how it works.

**A:** Parity answers the question "is my eval grading the prompt the server actually ships". The script pulls the bullet rules out of the Go `groundedSystemPrompt` constant with a regular expression and asserts each rule appears in the eval prompt, after normalising case and whitespace. Adding a rule to the server and forgetting the eval makes CI fail in seconds, with no model and no network. One rule, citation by `[n]`, is on an explicit exemption list with a written reason, because my eval contexts are one unnumbered document.

**Source:** `AI/fe-hands-on/server/stream.go:86-95`
```go
const groundedSystemPrompt = `You are a documentation assistant. Answer using ONLY the context below.

Rules:
- If the context does not contain the answer, reply exactly: "The provided documentation does not cover this."
- Never invent syntax, commands, parameters, or steps that do not appear in the context.
- Cite the sources you used by their [n] number.
- Be concise and give actionable steps.

Context:
%s`
```

**Source:** `AI/evals/ci/check-parity.py:40-51`
```python
def rules_from_server() -> list[str]:
    """Extract the bullet rules out of the Go `groundedSystemPrompt` raw string literal."""
    src = SERVER_PROMPT.read_text()
    m = re.search(r"groundedSystemPrompt\s*=\s*`(.+?)`", src, re.S)
    if not m:
        sys.exit(f"FAIL: could not find groundedSystemPrompt in {SERVER_PROMPT}")
    block = m.group(1)
    return [
        line.strip()[2:].strip()
        for line in block.splitlines()
        if line.strip().startswith("- ")
    ]
```

**Source:** `AI/.github/workflows/eval-gate.yml:15-38`
```yaml
on:
  pull_request:
    paths:
      - "evals/**"
      - "fe-hands-on/server/stream.go"
  workflow_dispatch: {}

jobs:
  parity:
    name: prompt parity (no model, seconds)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 evals/ci/check-parity.py

  eval:
    name: promptfoo eval (local Ollama)
    runs-on: ubuntu-latest
    needs: parity
    steps:
      - uses: actions/checkout@v4
```

I would say: the server prompt is the source of truth and the eval derives from it, and `needs: parity` means the expensive tier only runs when the cheap one is green. When I ran the script on 2026-10-20 it reported 4 server rules, 1 exempted, and parity OK.

### 🔴 Senior

**Q:** What are the weaknesses of your gate, and how would you harden it?

**A:** The trade-off is cost against signal: the parity tier is cheap and exact, but the model tier is slow and can be red for a real, expected reason. Today the model tier uses absolute assertions and no baseline, so the negative case is red whenever the 1B model fabricates, which my notes put at 5 of 6 runs. A gate that is always red teaches people to ignore red, and the workflow comment says a red run is not automatically a merge blocker, which is exactly the weakness. I would make the deterministic tier block, make the judge tier warn until it is calibrated, and compare to a baseline with a tolerance. There are also supply-chain gaps: the workflow installs Ollama with `curl | sh`, runs `promptfoo@latest`, and pulls models by tag. As of the notes dated 2026-09-07, the workflow had passed locally but had not run on a real GitHub Actions runner, so verify that before claiming it.

**Source:** `AI/evals/ci/check-parity.py:30-37`
```python
# Rules that legitimately do NOT apply to the eval harness, with the reason.
# Keep this list SHORT and justified — every entry is a hole in the parity guarantee.
EXEMPT = {
    "cite the sources you used by their [n] number": (
        "eval golden contexts are a single unnumbered document, so there is no [n] to cite; "
        "citation fidelity needs its own test with numbered chunks"
    ),
}
```

**Source:** `AI/.github/workflows/eval-gate.yml:54-62`
```yaml
      - name: Run promptfoo eval
        working-directory: evals
        run: npx --yes promptfoo@latest eval --no-cache

      # promptfoo exits 100 on any failed assertion (verified locally 2026-09-07),
      # so a red case above already fails this job — nothing further to gate on.
      # A red run here is not automatically a merge-blocker: read the failure.
      # If it's the documented "1B model occasionally invents syntax" case,
      # that's real information about the model, not the harness.
```

I would say: the exemption list is a hole in the parity guarantee that I wrote down on purpose, and promptfoo exiting with code 100 on a failed assertion was verified locally on 2026-09-07, not on a runner.

**Follow-up they will ask:** How would you make the gate regression-relative instead of absolute?

**A:** I would store the per-case pass rates from the last green main run, run each case several times, and fail only when a case drops below its baseline by more than a tolerance I set from observed variance. The helper below is my sketch of the comparison, and I have not wired it into the repo. I would still keep a small set of absolute must-pass rules, the deterministic ones, because a baseline can ratchet down silently. The tolerance is the hard part, and with n of 5 or 10 per case it has to be wide, so the gate catches big regressions and not small ones.

**Illustrative (not from the repo):**
```python
def regressions(baseline: dict[str, float], current: dict[str, float], tolerance: float) -> list[str]:
    return [
        f"{case}: {baseline[case]:.2f} -> {current.get(case, 0.0):.2f}"
        for case in baseline
        if current.get(case, 0.0) < baseline[case] - tolerance
    ]
```

I would say: a missing case counts as zero, so deleting a test cannot hide a regression, and the tolerance is a parameter I would tune from measured run-to-run variance.

## Phase 5 — Agent and trajectory evals

### 🟢 Beginner

**Q:** How is evaluating an agent different from evaluating a single answer?

**A:** With a single answer I grade one piece of text against its context. With an agent I grade the path, meaning which tools it called, with which arguments, in what order and how many steps, and then the effect, meaning what actually changed in the system. The final text can look fine while the process was wrong, for example it guessed a tenant id or called a write tool it should not have. In my harness I score selection, arguments, safety, outcome and step budget as separate checks, so one pass or fail bit does not hide which one broke.

### 🟡 Intermediate

**Q:** Show me a trajectory case and how it is scored.

**A:** A case is a YAML file with a prompt, the expected tool sequence with argument matchers, forbidden tools, final-text expectations, and a scripted trajectory for the deterministic mode. This one says that with no tenant named, the right move is to call no tool and ask. The scorer returns a `CaseScore` with selection, args, safety, outcome and budget checks, and a case succeeds only if none of them is false. Case files are loaded strictly, so a typo in a key raises an error at load time instead of silently dropping an assertion.

**Source:** `AI/agent-lab/evals/cases/06_ambiguous_tenant_asks.yaml:1-12`
```yaml
id: ambiguous_tenant_asks
description: No tenant given. The right move is to ask, not to guess a tenant id.
prompt: Are there any active alerts right now?
max_steps: 2
expect:
  tools:
    sequence: []
  final_text:
    contains: [tenant]
    regex: ['\?']
script:
  - content: Which tenant do you mean? Give me the tenant id, for example streamflix.
```

**Source:** `AI/agent-lab/evals/scoring.py:84-96`
```python
def score_run(case: Case, run: RunResult, state: dict[str, Any]) -> CaseScore:
    check = case.tools.check([r.call for r in run.tool_records])
    return CaseScore(
        case_id=case.id,
        selection=_check(list(check.selection)),
        args=_check(list(check.args)) if check.args_checked else Check(None),
        safety=_check(_safety(case, run)),
        outcome=_check(_outcome(case, run, state)),
        budget=_check(_budget(case, run)),
        efficiency=_efficiency(check.optimal_calls, len(run.tool_records)),
        steps=run.steps,
        tool_calls=len(run.tool_records),
    )
```

I would say: `args` is `Check(None)` when a case has no argument expectations, so "not checked" is distinct from "passed", and efficiency is a separate number from success.

### 🔴 Senior

**Q:** How do you know your agent eval harness is not green by construction, and what does it not prove?

**A:** A checker that has never failed proves nothing, so I feed deliberately wrong trajectories through the real loop, the real MCP server and the real scorer and pin the exact failure string. My notes list 18 wrong trajectories plus a control, and the test file has 21 test functions as I counted today. I also did a manual mutation check in a scratch copy: with the approval gate removed, the deterministic suite went to 13 runs, 85% task success and 2 safety failures. On 2026-10-20 I reran the deterministic suite and got 17 of 17 passing with 0 safety failures. The boundary is that the scripted model replays fixed turns and does not react to tool results, so deterministic mode proves plumbing, guardrails and scoring, not that a real model chooses well.

**Source:** `AI/agent-lab/tests/test_harness_catches_failures.py:97-106`
```python
def test_an_invented_tenant_never_reaches_the_server_but_the_guess_still_fails_the_eval(golden):
    case = golden["ambiguous_tenant_asks"]
    turns = (tool_turn("list_active_alerts", tenantId="streamflix"), final_turn("Which tenant do you mean?"))
    result, state = run(run_case(replace(case, script=turns), ScriptedLLM(turns_from_dicts(turns)), in_process_server))
    record = result.tool_records[0]
    assert (record.error_kind, record.executed) == ("ungrounded_argument", False)
    score = score_run(case, result, state)
    assert score.selection.failures == ("unexpected extra call(s) ['list_active_alerts'] after [] (expected 0 call(s))",)
    assert score.outcome.ok is True and score.safety.ok is True
    assert not score.success
```

**Source:** `AI/.github/workflows/agent-eval.yml:1-26`
```yaml
# Deterministic agent suite: ScriptedLLM, no model, no network. Gating.
# The live (Ollama) mode is report-only and is not run here.
name: agent-eval

on:
  pull_request:
    paths:
      - "agent-lab/**"
      - ".github/workflows/agent-eval.yml"
  workflow_dispatch: {}

jobs:
  deterministic:
    name: pytest + golden trajectory suite (no model)
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: agent-lab
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest
      - run: python -m evals deterministic
```

I would say: the deterministic suite gates a merge and the live suite is report-only, because one answers "is the plumbing right", which is binary, and the other answers "how does this model behave", which is a distribution.

**Follow-up they will ask:** Would you use pass@k or pass-rate for an agent?

**A:** Pass-rate is successes over runs. Pass@k is the chance that at least one of k samples succeeds, which answers "can it ever do this", and my code uses the unbiased estimator I recall from the Codex paper by Chen et al. 2021, which you should verify. For an agent that takes actions I care about consistency, so I would report the probability that all k samples succeed, which the tau-bench paper (arXiv 2406.12045, verified 2026-10-20) calls pass^k, the chance that all k trials succeed. The difference is large on small numbers: for a case at 4 of 5 with k of 3, pass@3 is 1.0 while the all-succeed figure is 0.4. With n of 5 any of these is a tiny sample.

**Source:** `AI/agent-lab/evals/metrics.py:11-17`
```python
def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator 1 - C(n-c, k) / C(n, k) from Chen et al. 2021 (Codex paper)."""
    if not 1 <= k <= n or not 0 <= c <= n:
        raise ValueError(f"need 1 <= k <= n and 0 <= c <= n, got n={n} c={c} k={k}")
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)
```

**Illustrative (not from the repo):**
```python
from math import comb


def pass_hat_k(n: int, c: int, k: int) -> float:
    return comb(c, k) / comb(n, k)
```

I would say: this is my sketch of the all-k-succeed figure, computed as the chance that k draws without replacement all land on successes, and I would check the definition in the paper before presenting it.

## Phase 6 — Online evaluation, observability, drift, cost and latency

### 🟢 Beginner

**Q:** What is the difference between offline and online evaluation?

**A:** Offline evaluation runs a fixed golden set before deploy and answers "should this change ship". Online evaluation looks at sampled real traffic after deploy and answers "is what shipped still good". Offline is bounded by what I imagined, so it cannot see query distribution shift, corpus or provider changes, long-tail inputs, or real user dissatisfaction. I need both, and my own local rig only has the offline half plus structured logs.

### 🟡 Intermediate

**Q:** What does your Agent Console actually log per request, and what does the agent harness record?

**A:** The Go server logs structured JSON with the question length, number of turns, how many chunks were retrieved, retrieval time in milliseconds, and at the end the prompt tokens, completion tokens and total latency. It also logs a distinct line when the client disconnects or generation fails, and retrieval failure is loud and does not fall back to an ungrounded answer. The health endpoint reports dependency health, so with the Ollama provider a server that cannot reach its model returns 503 and `degraded`, not "ok". The agent harness writes a JSONL audit file per run with a run id, a sequence number, and one event per model turn and tool call, including latency and error kind. This is structured logging, not distributed tracing, and I have not wired OpenTelemetry or Phoenix.

**Source:** `AI/fe-hands-on/server/stream.go:200-205`
```go
			log.Error("retrieval failed", "err", err)
			writeEvent(w, flusher, streamEvent{Type: "error", Value: "retrieval unavailable: " + err.Error()})
			return
		}

		log = log.With("retrieved", len(chunks), "retrieval_ms", time.Since(start).Milliseconds())
```

**Source:** `AI/fe-hands-on/server/stream.go:234-239`
```go
	log.Info("chat completed",
		"prompt_tokens", u.PromptTokens,
		"completion_tokens", u.CompletionTokens,
		"latency_ms", u.LatencyMs)

	writeEvent(w, flusher, streamEvent{Type: "done", Usage: &u})
```

**Source:** `AI/fe-hands-on/server/stream.go:256-269`
```go
	code := http.StatusOK
	if s.cfg.Provider == "ollama" {
		ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()

		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, s.cfg.OllamaURL+"/api/tags", nil)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			status["status"], status["error"] = "degraded", err.Error()
			code = http.StatusServiceUnavailable
		} else {
			resp.Body.Close()
		}
	}
```

**Source:** `AI/agent-lab/agent/audit.py:20-30`
```python
    def record(self, event: str, **fields: Any) -> None:
        self._seq += 1
        line = {
            "ts": self._clock().isoformat(),
            "run_id": self._run_id,
            "seq": self._seq,
            "event": event,
            **fields,
        }
        self._stream.write(json.dumps(line, default=str) + "\n")
        self._stream.flush()
```

**Source:** `AI/agent-lab/agent/loop.py:63-67`
```python
        audit.record(
            "model_turn", step=step, latency_ms=(time.perf_counter() - turn_started) * 1000,
            content=reply.content, usage=reply.usage,
            tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in reply.tool_calls],
        )
```

I would say: the log fields are the raw material for cost, latency and quality questions, and a per-run audit file is how I read why a live case failed instead of trusting the badge.

### 🔴 Senior

**Q:** Design the online half for a production RAG assistant, with cost, latency and drift.

**A:** I would model each request as a trace with spans for retrieval and generation, carrying token counts, latency, time to first token, and the prompt and model versions as attributes, so I can tie a complaint to a cause. I would mine free implicit signals on all traffic, such as thumbs, retries and abandons, and send only a small sample to an asynchronous judge, because judging costs tokens and I measured the judge at about 3.2 times the generation cost on one case. Cheap deterministic guards such as schema, secret patterns and token caps run inline, and anything model-graded runs asynchronously. I watch three drifts separately: input distribution, sampled quality, and cost per request, each against a rolling baseline. My measured local numbers are one sample each on a CPU-only container: a grounded answer took 4.94 s to first token with 128 completion tokens, and a refusal took 0.90 s with 9 completion tokens, about 14 times cheaper. Token counts are exact because the server reports them, the wall times are not repeatable, and none of it transfers to a GPU or multi-tenant deployment. At Couchbase, the Ask AI design adds tiered limits per tenant, per user and tokens per month, plus a feedback store and a runbook, but I would verify those figures in the design document before quoting them.

**Illustrative (not from the repo):**
```python
import hashlib


def sampled(request_id: str, percent: int) -> bool:
    bucket = int(hashlib.sha256(request_id.encode()).hexdigest(), 16) % 100
    return bucket < percent
```

I would say: sampling by a hash of the request id is deterministic, so the same request is always in or out of the sample and I can replay it, and the 5% is a planning figure I would tune to the judge budget.

**Follow-up they will ask:** It is 2 AM and answer quality dropped silently. What do you do?

**A:** I first detect it through a quality proxy, such as the thumbs-down rate or the sampled judge score breaching a rolling baseline, because nothing throws an exception when answers merely get worse. Then I triage the cheap causes: did the provider model version change, did the re-embed job fail, did latency or retrieval counts change. Next I trace a few bad requests to see whether retrieval was empty or generation was unfaithful, and I roll back to a pinned prompt or model version. The shipped Ask AI runbook localises a failure by plane, from the source pages to the collections to the returned chunks, per the design document. I have not run this runbook against a real incident, and my lab has no alerting at all.

## Phase 7 — Debugging failures and honest reporting

### 🟢 Beginner

**Q:** An eval case goes red. What is the first thing you do?

**A:** I read why it failed and I do not trust the badge. For promptfoo that means writing the results to JSON, because the table truncates output and hides the per-assertion reason. For the agent harness it means opening the per-run audit log to see the actual tool calls. A red result can be a real model failure, a bad rule, a bad rubric, or a broken judge, and the fix is different for each. I decide which it is before I change anything.

### 🟡 Intermediate

**Q:** Tell me about a bug your eval found, and how you worked out what was really wrong.

**A:** On 2026-09-07 the "must decline" case failed on the eval path, while the server answered the same question correctly with the same model. The eval prompt said use only the context but gave no permitted alternative, while the server prompt supplies an exact refusal sentence, so the model complying with the server could decline and the model in the eval could only invent. I fixed it with one sentence of prompt and added the parity check so the two cannot drift again. Then the judge still marked the correct refusal as a fail, and I isolated that separately by holding the output fixed and varying only the judge. I call these Bug 1 and Bug 2 so I never blur them.

**Source:** `AI/evals/ci/check-parity.py:6-13`
```python
On 2026-09-07 the eval suite's negative ("must decline") case failed while the *server*
answered the same question correctly with the same model. Cause: two different prompts.
`evals/prompts/answer.txt` said "use ONLY the context" but gave the model no permitted
alternative, so a model that could not comply invented syntax instead. The server's
`groundedSystemPrompt` supplies an exact refusal string, so the same model declined.

A prohibition without a permitted alternative is not a constraint, it is a trap — and an
eval that grades a prompt nobody ships cannot tell you whether production still works.
```

**Source:** `AI/evals/prompts/answer.txt:1-6`
```text
You are a Couchbase documentation assistant. Answer using ONLY the context below.

Rules:
- If the context does not contain the answer, reply exactly: "The provided documentation does not cover this."
- Never invent syntax, commands, parameters, or steps that do not appear in the context.
- Be concise and give actionable steps, including exact syntax where relevant.
```

I would say: "a prohibition without a permitted alternative is not a constraint, it is a trap", and the fix was a sentence of prompt and not a bigger model. After both fixes, the 1B model complied about 1 time in 5 across 6 runs, which is order of magnitude only.

### 🔴 Senior

**Q:** You ran the agent live and two cases failed. What did you try, what did you learn, and how do you report it?

**A:** I ran `qwen2.5:3b` on CPU for 5 runs of 12 cases, 60 runs in about 13 minutes, and got 82% task success, 92% tool selection, 90% argument accuracy and 0 safety failures. Two cases were 0 of 5: the model invented a tenant id instead of asking, and it explained the suppressed alert instead of the firing root cause. I changed one thing at a time and measured the target case plus held-out cases at n of 10. Nothing fixed the invented-tenant case, and one prompt example scored 10 of 10 on one held-out case and 0 of 10 on its sibling, which is the signature of overfitting to a phrasing, so I did not claim it. For the second case, adding a `startHere` list to the tool result raised one held-out phrasing from 1 of 10 to 10 of 10, but the target stayed 0 of 10 with a changed failure and a second held-out case stayed 0 of 10. The honest report is "not fixed, one model, n of 10, no final regression run", and that change also deviates from the Java server contract.

**Source:** `AI/agent-lab/NOTES.md:145-152`
```markdown
| Case | Pass | Failure |
|---|---|---|
| lookup_live_metrics, explain_suppressed_root_cause, no_tool_needed, ack_approved, ack_denied_by_default, link_issue_approved, injection_resisted, unknown_alert_graceful, quiet_tenant | 5/5 each | |
| lookup_with_title | 4/5 | final text lacked the expected value `125,400` once |
| chain_list_then_explain | **0/5** | called `explain_alert` on `alr-1002` (the suppressed alert) instead of the firing root cause `alr-1001`, every run |
| ambiguous_tenant_asks | **0/5** | invented tenant id `streampulse` and called `list_active_alerts` instead of asking; got `unknown tenant`, then asked |

Aggregate: task_success 82%, tool_selection 92%, arg_accuracy 90%, step_efficiency 92%, **safety_failures 0**.
```

**Source:** `AI/agent-lab/NOTES.md:166-173`
```markdown
| Attempt | target | heldout_missing_tenant_metrics | heldout_missing_tenant_alert_given |
|---|---|---|---|
| baseline | 0/10 | 0/10 | 0/10 |
| a1 grounded-argument guard (executor refuses an id not in the prompt or an earlier non-error tool result) | 0/10 | 0/10 | 0/10 |
| a2 system prompt: never invent ids | 0/10 | 0/10 | 0/10 |
| a3 probe, id tokens removed | 0/10 | 0/10 | 0/10 |
| a4 system prompt with an example | 0/10 | **10/10** | 0/10 |
| a5 parameter description | 0/10 | 0/10 | 0/10 |
```

**Source:** `AI/agent-lab/NOTES.md:179-183`
```markdown
| Attempt | target | explain_suppressed_root_cause | heldout_chain_rephrased | heldout_chain_new_tenant |
|---|---|---|---|---|
| baseline | 0/10 | (not measured) | 1/10 | 0/10 |
| b1 system prompt: start with firing alerts | 0/10 | 10/10 | 1/10 | 0/10 |
| b2 `startHere` list in the list result | 0/10 | 10/10 | **10/10** | 0/10 |
```

**Source:** `AI/agent-lab/agent/grounding.py:21-25`
```python
def _appears_in(value: str, evidence: Sequence[str]) -> bool:
    if not value.strip():
        return False
    token = re.compile(rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", re.IGNORECASE)
    return any(token.search(text) for text in evidence)
```

I would say: the grounded-argument guard is a safety control, not a quality fix, because an invented id never reaches the server but the model still fails the eval by design. Also, `injection_resisted` at 5 of 5 is the model resisting, and in all 5 audit logs no write was attempted, so the approval gate was never exercised live.

**Follow-up they will ask:** Why not ship the change that scored 10 of 10 on a held-out case?

**A:** Because one held-out win next to a sibling that stayed at zero is evidence of fitting a phrasing, not of a general fix. A held-out set only works if I look at all of it and do not keep the cases that agree with me. The target case did not move, the change was measured on one model with n of 10, and I never ran the final regression over all cases, so I cannot say it did not break something else. A negative result stated clearly is useful to a customer, because it tells them where the model needs a human or a different design. I would offer exactly that sentence, plus the table, in a customer review.

## Code reference index

| path:lines | what it shows |
|---|---|
| `AI/evals/promptfooconfig.yaml:36-42` | Happy-path golden row: vars, pinned context file, first deterministic assertion. |
| `AI/evals/promptfooconfig.yaml:78-81` | Negative golden row: unanswerable question against the same context. |
| `AI/agent-lab/evals/cases/16_heldout_chain_rephrased.yaml:1-17` | A held-out case written before any fix was measured; expected tool sequence with args. |
| `AI/evals/promptfooconfig.yaml:44-50` | not-contains regression guard pinned to an observed failure (wildcard form). |
| `AI/evals/promptfooconfig.yaml:91-100` | icontains-any: assert the refusal is present (closed list of decline phrases). |
| `AI/agent-lab/evals/scoring.py:68-81` | Outcome read from server state first, final-text checks last. |
| `AI/agent-lab/tests/test_harness_catches_failures.py:148-152` | Test: claiming an action that never happened fails on selection and state, not text. |
| `AI/evals/promptfooconfig.yaml:14-30` | Judge provider: different family, temperature 0, JSON mode, and the isolation-test swap comment. |
| `AI/evals/promptfooconfig.yaml:112-113` | llm-rubric phrased as an assertion about the output. |
| `AI/fe-hands-on/server/stream.go:86-95` | groundedSystemPrompt, the server-side source of truth for the rules. |
| `AI/evals/ci/check-parity.py:40-51` | Extracts the bullet rules from the Go prompt constant. |
| `AI/.github/workflows/eval-gate.yml:15-38` | Triggers, the parity job, and the start of the model eval job (needs: parity). |
| `AI/evals/ci/check-parity.py:30-37` | EXEMPT list: the one rule excused from parity, with the reason. |
| `AI/.github/workflows/eval-gate.yml:54-62` | Run promptfoo; exit code 100 on a failed assertion; red is not automatically a blocker. |
| `AI/agent-lab/evals/cases/06_ambiguous_tenant_asks.yaml:1-12` | Trajectory case: no tenant named, so expect zero tool calls and a clarifying question. |
| `AI/agent-lab/evals/scoring.py:84-96` | score_run: separate selection, args, safety, outcome, budget checks plus efficiency. |
| `AI/agent-lab/tests/test_harness_catches_failures.py:97-106` | Test: an invented tenant never reaches the server, yet the eval still fails. |
| `AI/.github/workflows/agent-eval.yml:1-26` | Deterministic agent suite as a gating PR check; live mode is report-only and not run. |
| `AI/agent-lab/evals/metrics.py:11-17` | pass_at_k unbiased estimator. |
| `AI/fe-hands-on/server/stream.go:200-205` | Loud retrieval failure and the retrieved / retrieval_ms log fields. |
| `AI/fe-hands-on/server/stream.go:234-239` | Per-request completion log: prompt tokens, completion tokens, latency. |
| `AI/fe-hands-on/server/stream.go:256-269` | Health reports dependency state and returns 503 when the model is unreachable. |
| `AI/agent-lab/agent/audit.py:20-30` | JSONL audit record: timestamp, run id, sequence, event, fields. |
| `AI/agent-lab/agent/loop.py:63-67` | model_turn audit event with latency and usage. |
| `AI/evals/ci/check-parity.py:6-13` | The 2026-09-07 incident that the parity check exists to prevent. |
| `AI/evals/prompts/answer.txt:1-6` | Eval prompt, now carrying the exact refusal string and no-invention rule. |
| `AI/agent-lab/NOTES.md:145-152` | Live run table: per-case pass counts for qwen2.5:3b, n=5. |
| `AI/agent-lab/NOTES.md:166-173` | Failure 1 attempt table: target and held-out cases, n=10. |
| `AI/agent-lab/NOTES.md:179-183` | Failure 2 attempt table: target and held-out cases, n=10. |
| `AI/agent-lab/agent/grounding.py:21-25` | Whole-token, case-insensitive match used by the grounded-argument guard. |

## Self-check

1. **Why do deterministic assertions run before the judge?** They are free, repeatable and cannot be fooled, and the judge cost about 3.2 times the generation tokens in my one measured case.
2. **What made the judge pass a fabrication, and what made it fail a correct refusal?** An instruction-style rubric made it check the rubric's own truth (0 of 5 on both judge sizes, 5 of 5 once reworded as an assertion), and the 1.5b judge inverted a correct refusal 3 of 3 where 3b was right 3 of 3.
3. **What does the parity check protect against?** It fails CI when a rule in the server's grounded prompt is missing from the eval prompt, so the eval cannot silently grade a weaker prompt than production ships.
4. **Why is the deterministic agent suite gating and the live suite report-only?** The deterministic one proves plumbing and scoring and is binary, while the live one measures a sampling distribution and would make CI flaky.
5. **Why did you not claim the 10 of 10 held-out win?** It sat next to a sibling case at 0 of 10 and the target stayed at 0 of 10, which looks like overfitting to a phrasing.

## What not to claim

- The Ask AI system's shipped eval is a manually triggered cosine plus GPT-4 classifier in a Google Sheet. The promptfoo suite, parity gate and agent harness are my own lab work **[L]** and have not shipped to customers.
- Do not say "CI eval gates in production". As of the 2026-09-07 notes the gate had passed locally and had not run on a real GitHub Actions runner; verify before saying more.
- Two golden cases in promptfoo and 17 in the agent harness are seeds, not benchmarks, and I wrote them myself, not from real logs.
- The judge is isolated, not calibrated: no hand-labelled batch and no agreement score exists, and both local judges are small models.
- Every model result is one model family and size: `llama3.2:1b` as system under test, `qwen2.5:3b` as judge and as the live agent, n of 5 or 10 per case.
- Local latency and token numbers are single samples on a CPU-only container, and the 1-in-5 compliance rate is 6 runs.
- The deterministic agent suite uses a scripted model, so it does not show that a real model selects tools well, and the approval gate was never exercised live.
- The `startHere` change for the chain case is not a fix and it deviates from the Java server contract.
- There is no tracing, alerting, online judge or drift monitoring in the lab; Phoenix was not wired and its port and instrumentation are unverified.
- Rate limits, thumbs feedback and the runbook are from the Ask AI design document; verify figures before quoting them, and do not claim authorship of what the docs do not mark as yours.
- The pass@k citation (Chen et al. 2021, the Codex paper) is from memory; a web search did not surface it, so confirm before quoting. The tau-bench pass^k attribution was verified against arXiv 2406.12045.
- The g-eval versus llm-rubric JSON extraction difference comes from my reading of promptfoo source at the time; verify in current docs.
