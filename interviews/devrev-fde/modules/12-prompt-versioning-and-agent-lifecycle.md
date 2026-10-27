# Module 12 — Prompt versioning & the agent lifecycle

> This module is the prompt registry I built in `agent-lab/promptreg`: a small file-based Python package that stores every system prompt as an immutable numbered version, resolves which version a run gets (explicit, pinned, canary or production), refuses to promote a version unless an eval gate allows it, and records which exact prompt a run used. Everything here is lane [L], my own build, with a core that uses only the standard library, no network and no model, except the live comparison, which imports the eval harness and talks to a local Ollama. I wrote it because the agent from module 03 had its system prompt as a hard-coded constant, and I had already seen a prompt change move results (module 03, phase 1). It is a lab registry, not a product: it is not wired into the agent's default runtime path, which still uses the constant, and the only live measurement of two prompt versions is n=5 on one small model (`qwen2.5:3b` through Ollama). Hosted prompt-management products exist, I did not use any, and I make no comparison with them. The code lives in `AI/agent-lab/promptreg/` and the tests in `AI/agent-lab/tests/test_promptreg_*.py`; the seeded data is in `AI/agent-lab/prompts/system/`.

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. Versioned prompts | Store every prompt as a numbered file with a hash, an author, a changelog and an append-only history. | `promptreg/store.py`, `promptreg/registry.py` |
| 2. Immutability and tamper detection | A version is written once, and a read fails if the file no longer matches its recorded hash. | `promptreg/store.py` |
| 3. Pinning, resolution order and rollback | One function decides which version a run gets, a pin overrides it, and rollback walks back through history. | `promptreg/registry.py` |
| 4. Canary and shadow (bucketing) | Send a stable, deterministic share of run keys to a candidate version before it is production. | `promptreg/bucketing.py`, `promptreg/registry.py` |
| 5. Eval-gated promotion | Production moves only when two eval reports pass the gate, and the decision and its evidence are written to history. | `promptreg/gate.py`, `promptreg/registry.py`, `evals/ci/check-parity.py` |
| 6. Provenance | A run can say which prompt name, version and hash it used, and why that version was chosen. | `promptreg/provenance.py`, `agent/audit.py` |
| 7. Honest comparison | Compare two versions on the same cases and model, and print counts with a 95% interval, not one bare percentage. | `promptreg/live_compare.py`, `promptreg/stats.py` |

## Phase 1 — Versioned prompts: files, an index and a history

### 🟢 Beginner

**Q:** What does it mean to version a prompt, and why would you do it?

**A:** A prompt is behaviour written as text: changing one sentence can change which tool the model calls or whether it asks a question. Versioning means every wording gets a number, a hash of its exact bytes, an author and a note, and it is saved so I can say which text a run used and go back to an earlier one. In agent-lab the system prompt was a constant in `agent/loop.py`. I copied it byte for byte into `prompts/system/v1.md` as the baseline, and a test fails if the two ever differ. So version 1 is a known starting point, and version 2 is a candidate that I can measure against it.

### 🟡 Intermediate

**Q:** How is a prompt stored, and what happens when you add a new version?

**A:** Each prompt name is a directory with three kinds of files: `v<N>.md` holds the text, `index.json` holds the metadata and the aliases, and `history.jsonl` is an append-only list of events. The flow of control for `add_version` is the registry calling the store, which picks the next number, writes the file, records its hash, author, changelog and timestamp in the index, and saves the index. If the prompt has no production version yet, the registry then makes the new version production and appends a `bootstrap` event, so the first version added is live immediately. The timestamp comes from an injected clock, so the tests assert exact times. The data flow is text in, a hash and a number out, and the seed test proves the stored v1 is byte-identical to the constant in `agent/loop.py`.

**Source:** `AI/agent-lab/promptreg/store.py:26-40`

```python
@dataclass(frozen=True)
class VersionMeta:
    sha256: str
    created_at: str
    author: str
    changelog: str


@dataclass
class PromptIndex:
    versions: dict[int, VersionMeta] = field(default_factory=dict)
    production: int | None = None
    canary: int | None = None
    canary_percent: int = 0
    pin: int | None = None
```

**Source:** `AI/agent-lab/promptreg/registry.py:22-29`

```python
    def add_version(self, name: str, text: str, author: str, changelog: str, version: int | None = None) -> int:
        number = self._store.add_version(name, text, author, changelog, version)
        index = self._store.load_index(name)
        if index.production is None:
            index.production = number
            self._store.save_index(name, index)
            self._store.append_history(name, "bootstrap", to=number)
        return number
```

**Source:** `AI/agent-lab/tests/test_promptreg_seed.py:9-10`

```python
def test_v1_of_the_seeded_system_prompt_is_byte_identical_to_the_one_in_loop_py():
    assert (PROMPTS_DIR / "system" / "v1.md").read_bytes() == SYSTEM_PROMPT.encode("utf-8")
```

I would point at `PromptIndex`: it holds every version's hash plus the three alias fields, production, canary and pin, so the whole state of one prompt is one small JSON file a human can read, and a test pins that shape.

### 🔴 Senior

**Q:** What did you trade away by using files in a directory instead of a database or a service?

**A:** What I gained is a registry that needs no infrastructure, whose diffs are reviewable in a pull request, and whose text sits in the same commit as the code that uses it. What I gave up is concurrency control. The index is read, changed in memory and written back, so by my reading two people changing aliases at the same time can lose one update, and I did not write a test for that. The write goes to a temporary file and is swapped in with `os.replace`, which I believe is atomic on one POSIX filesystem, so a reader never sees half an index; verify that in the Python and OS documentation before relying on it. The temporary file name is fixed, so two writers could also collide on it. History is appended without an fsync, so I would not claim durability across power loss. The boundary is a single writer on a local filesystem, with one seeded prompt named `system`, and 86 `promptreg` tests that pass on my machine.

**Source:** `AI/agent-lab/promptreg/store.py:85-90`

```python
    def save_index(self, name: str, index: PromptIndex) -> None:
        directory = self._dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "index.json.tmp"
        temporary.write_text(json.dumps(index.to_json(), indent=2) + "\n")
        os.replace(temporary, directory / "index.json")
```

**Follow-up they will ask:** How would two services running on different machines share this registry?

**A:** As built they would not: each would read its own copy of the files, so a promotion would only reach a service on its next deploy. I would move the store behind an interface with a shared backend, keep the same immutable-version rules, and add a compare-and-set on the index so alias changes cannot overwrite each other. `PromptStore` is already the only class that touches the disk, so that is a change in one place, but I have not built or tested it.

## Phase 2 — Immutability and tamper detection

### 🟢 Beginner

**Q:** What does it mean that a prompt version is immutable, and why does it matter?

**A:** Once version 3 exists, its text never changes; if the wording needs a fix, the fix is version 4. It matters for two reasons. History stays truthful, because "run X used v3" always means the same words. And an eval result stays attached to the exact text it measured. In my code, writing to a version number that already exists raises `VersionExists`, and reading a version whose file no longer matches its recorded hash raises `TamperError`.

### 🟡 Intermediate

**Q:** How is immutability enforced in the code, and what does it protect?

**A:** There are two enforcement points. On write, the store opens the version file in exclusive-create mode, `"xb"`, so it fails if the file exists even when the index does not list it, and a test creates such an orphan file and sees the next add refused with the orphan untouched. On read, the store recomputes the SHA-256 of the file and compares it with the hash in the index. Every path that uses a version goes through that read: resolving a run, promoting and rolling back. So a quietly edited file cannot be served, promoted or rolled back to; tests cover each of the three. The prompt name also becomes a directory name, so a regular expression rejects names such as `../escape` or `a/b` before any path is built.

**Source:** `AI/agent-lab/promptreg/store.py:92-108`

```python
    def add_version(self, name: str, text: str, author: str, changelog: str, version: int | None = None) -> int:
        directory = self._dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        index = self.load_index(name) if (directory / "index.json").is_file() else PromptIndex()
        number = version if version is not None else max(index.versions, default=0) + 1
        if number < 1:
            raise PromptRegError(f"version must be >= 1, got {number}")
        if number in index.versions:
            raise VersionExists(f"{name} v{number} already exists and is immutable")
        try:
            with (directory / f"v{number}.md").open("xb") as handle:
                handle.write(text.encode("utf-8"))
        except FileExistsError:
            raise VersionExists(f"{name} v{number}.md already exists on disk and is immutable") from None
        index.versions[number] = VersionMeta(sha256_hex(text), self._clock().isoformat(), author, changelog)
        self.save_index(name, index)
        return number
```

**Source:** `AI/agent-lab/promptreg/store.py:110-118`

```python
    def read_version(self, name: str, version: int) -> tuple[str, str]:
        meta = self.load_index(name).versions.get(version)
        if meta is None:
            raise UnknownPrompt(f"{name} has no version {version}")
        text = (self._dir(name) / f"v{version}.md").read_bytes().decode("utf-8")
        actual = sha256_hex(text)
        if actual != meta.sha256:
            raise TamperError(f"{name} v{version} was modified: recorded sha256 {meta.sha256}, file has {actual}")
        return text, meta.sha256
```

**Source:** `AI/agent-lab/tests/test_promptreg_store.py:47-54`

```python
def test_reading_a_version_whose_file_changed_raises_tamper_error(tmp_path):
    registry, store = new_registry(tmp_path)
    registry.add_version("system", "original", "x", "c")
    (tmp_path / "system" / "v1.md").write_text("original, quietly edited")
    with pytest.raises(TamperError, match="v1 was modified"):
        store.read_version("system", 1)
    with pytest.raises(TamperError):
        registry.resolve("system", "any-run")
```

I would point at the `TamperError` line: it prints the recorded hash and the hash of what is on disk, so the person on call can see immediately that the file changed and not the index.

**Q:** Why does the name check exist?

**A:** Because the name is used as a path segment, and a name containing a slash or two dots could write outside the store directory. The pattern allows lowercase letters, digits, underscore and hyphen, up to 64 characters, and a parametrised test feeds it six bad names.

**Source:** `AI/agent-lab/promptreg/store.py:68-72`

```python
    def _dir(self, name: str) -> Path:
        # The name becomes a path segment, so it must never contain '/' or '..'.
        if not NAME_PATTERN.match(name):
            raise PromptRegError(f"invalid prompt name {name!r}: use lowercase letters, digits, '_' or '-'")
        return self._root / name
```

### 🔴 Senior

**Q:** How strong is the tamper detection, and what does failing closed cost you?

**A:** It detects accidental or careless edits; it does not prevent a determined one. The hash lives in `index.json` next to the files, so anyone who can edit `v1.md` can also edit the index and make them agree. The real backstop is code review and git history, which are outside this package. Failing closed means a tampered version raises instead of being served, so a bad edit takes the agent down and does not silently run unreviewed text. That is the trade between integrity and availability, and a production system would want an alert and a fallback to the last known good version, which I did not build. Every resolve reads the file and hashes it; I did not measure the cost, and for a prompt of a few hundred bytes I expect it to be small, but I have no number.

**Source:** `AI/agent-lab/prompts/system/index.json:9-14`

```json
    "2": {
      "sha256": "1d43fd3c5bee29ca33608fe5ab35369c527f8b2427a0d9b5c9462a81297404d6",
      "created_at": "2026-10-20T02:36:57.325828+00:00",
      "author": "aashish",
      "changelog": "Candidate: adds guidance for the two live failures in NOTES.md (ask for a missing tenant id; start with firing alerts / startHere). UNMEASURED at creation; any later measurement is kept as an evidence file, not by editing this entry."
    }
```

I would point at the changelog of version 2: it says "UNMEASURED at creation; any later measurement is kept as an evidence file, not by editing this entry". Immutability here covers the metadata as well, so a measurement goes into a new file and a stated claim is never rewritten after the fact.

**Follow-up they will ask:** Someone edits `v1.md` in place to fix a typo. What happens, and what should they have done?

**A:** The next resolve, promote or rollback that reads v1 raises `TamperError` and names both hashes, so production for that prompt fails closed until someone acts. They should have added the corrected text as a new version, then taken it through the gate. The cost is that a one-word fix goes through an eval cycle, which is slow; for an emergency I would pin a known good version while the fix is measured.

## Phase 3 — Pinning, resolution order and rollback

### 🟢 Beginner

**Q:** What is pinning, and when would you use it?

**A:** Pinning forces every run of one prompt name onto a single version until someone clears the pin. I would use it to freeze behaviour while I investigate an incident, to reproduce a bug against the exact prompt that caused it, or to keep a cautious customer on a tested wording. A pin does not change which version is production; it only overrides which version a run receives. An explicit version asked for in the call beats everything, including a pin.

### 🟡 Intermediate

**Q:** How does the registry decide which version a run gets, and how does rollback work?

**A:** `resolve` takes the prompt name, a run key and an optional explicit version, and returns a `PromptRef` with the version, the hash, the text and a reason string. The order is fixed: an explicit version, then a pin, then the canary if one is set and the run key falls in its bucket, then production. If there is no production version it raises a `StateError`. The reason string says why, for example "pinned to 2", and it is what later lands in the audit log. Rollback does not just subtract one from the version number: it replays the history, treating `bootstrap` and `promote` as pushes onto a stack of production versions and `rollback` as a pop, then moves production to the entry below the top. It refuses if the history's top and the index disagree, or if there is nothing below, and it refuses to restore a tampered version.

**Source:** `AI/agent-lab/promptreg/registry.py:35-48`

```python
    def resolve(self, name: str, run_key: str, version: int | None = None) -> PromptRef:
        index = self._store.load_index(name)
        if version is not None:
            return self._ref(name, version, f"explicit version {version}")
        if index.pin is not None:
            return self._ref(name, index.pin, f"pinned to {index.pin}")
        if index.production is None:
            raise StateError(f"{name} has no production version")
        if index.canary is None or index.canary_percent == 0:
            return self._ref(name, index.production, "production: no canary configured")
        slot = bucket(name, run_key)
        if slot < index.canary_percent:
            return self._ref(name, index.canary, f"canary: bucket {slot} < {index.canary_percent}")
        return self._ref(name, index.production, f"production: bucket {slot} >= {index.canary_percent}")
```

**Source:** `AI/agent-lab/promptreg/registry.py:129-147`

```python
    def rollback(self, name: str) -> int:
        index = self._store.load_index(name)
        stack: list[int] = []
        for event in self._store.read_history(name):
            if event["event"] == "rollback":
                stack = stack[:-1]
            elif event["event"] in PRODUCTION_EVENTS:
                stack.append(event["to"])
        if not stack or stack[-1] != index.production:
            history_says = stack[-1] if stack else None
            raise StateError(f"{name}: history says production is {history_says}, index says {index.production}")
        if len(stack) < 2:
            raise StateError(f"{name} has no earlier production version to roll back to")
        target = stack[-2]
        self._store.read_version(name, target)
        index.production = target
        self._store.save_index(name, index)
        self._store.append_history(name, "rollback", **{"from": stack[-1], "to": target})
        return target
```

**Source:** `AI/agent-lab/tests/test_promptreg_resolution.py:64-69`

```python
def test_an_explicit_version_beats_a_pin_and_a_canary(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, 100)
    registry.pin("system", 2)
    ref = registry.resolve("system", "run", version=1)
    assert (ref.version, ref.reason, ref.text) == (1, "explicit version 1", "stable text")
```

I would point at the order of the `if` statements in `resolve`: the precedence is the code's own order, and the two tests that pin it are the explicit-beats-pin test and the pin-beats-canary-until-cleared test.

### 🔴 Senior

**Q:** What are the sharp edges of pin and rollback?

**A:** They are different tools and mixing them up is the failure mode. A pin is a global override on one prompt name that masks both production and the canary without changing either, and I would not call it per-customer, because the registry has no notion of a customer. A pin left on by mistake makes later promotions look like they did nothing, since `resolve` returns the pin before it looks at production; the `list` command prints `pin=vN`, which is the only warning. Rollback moves only the production alias. By my reading of `rollback`, it does not touch the canary or the pin, so rolling back while a bad canary is still configured leaves the canary running; the fix for a bad canary is `canary --clear`, not rollback. I tested the rollback stack, including a promote after a rollback, but I did not test rollback with a canary or a pin set. The boundary is that history is the source of truth for rollback, so a hand-edited index makes it refuse, which is deliberate.

**Source:** `AI/agent-lab/tests/test_promptreg_registry.py:146-155`

```python
def test_rollback_walks_back_one_step_at_a_time_and_stops_at_the_first_version(tmp_path):
    registry, store = setup(tmp_path, texts=("one", "two", "three"))
    candidate, baseline = reports(tmp_path, BETTER)
    registry.promote("system", 2, candidate, baseline, Gate())
    registry.promote("system", 3, candidate, baseline, Gate())
    assert registry.rollback("system") == 2
    assert registry.rollback("system") == 1
    with pytest.raises(StateError, match="no earlier production"):
        registry.rollback("system")
    assert store.load_index("system").production == 1
```

**Follow-up they will ask:** Why derive rollback from history instead of keeping a "previous production" field?

**A:** A field can drift from what really happened, and it only remembers one step back. The history is already the append-only record of every production change, so replaying it gives any number of steps and gives a check against the index at the same time. The price is that a missing or hand-edited history line breaks rollback, and a half-written line would make the history unreadable by my reading of `read_history`; I did not test that.

## Phase 4 — Canary and shadow: deterministic bucketing

### 🟢 Beginner

**Q:** What is a canary release of a prompt, and what is shadow mode?

**A:** A canary sends a small share of runs to the new version first, so a bad change hurts a few runs instead of all of them. Shadow mode runs the candidate on the same input beside production but never shows its answer, so you can compare without any user risk. In my lab the canary is built into `resolve`. Shadow is only half built: `resolve_shadow` returns the production version and the candidate as a pair, but nothing in the repo runs the second one or compares the two answers; the only callers are the CLI and the tests.

### 🟡 Intermediate

**Q:** How do you decide which runs go to the canary, and why is it deterministic?

**A:** The bucket is the first eight hex digits of the SHA-256 of the prompt name, a colon and the run key, read as a number and taken modulo 100. A run goes to the canary when its bucket is below the canary percentage, so the same run key always lands on the same version. Including the prompt name in the hash means two different prompts do not send the same users to their canaries. The boundary is exact: with 10 percent, bucket 9 gets the canary and bucket 10 stays on production, and a test checks both. Tests also show that over 10,000 keys the canary share stays within 1.5 percentage points of 5, 10 and 50 percent, and that raising the percentage only adds keys, it never moves one back. The flow of control is the one in phase 3, with the canary branch taken only when a canary version is set and the percentage is above zero.

**Source:** `AI/agent-lab/promptreg/bucketing.py:6-8`

```python
def bucket(name: str, run_key: str) -> int:
    digest = sha256(f"{name}:{run_key}".encode()).hexdigest()
    return int(digest[:8], 16) % 100
```

**Source:** `AI/agent-lab/tests/test_promptreg_resolution.py:34-39`

```python
@pytest.mark.parametrize("percent", [5, 10, 50])
def test_canary_share_over_10k_keys_is_within_1_5_points_of_the_percentage(tmp_path, percent):
    registry, _ = registry_with_two_versions(tmp_path)
    registry.set_canary("system", 2, percent)
    canary = sum(registry.resolve("system", f"user-{i}").version == 2 for i in range(10_000))
    assert abs(canary / 100 - percent) <= TOLERANCE_POINTS
```

**Source:** `AI/agent-lab/tests/test_promptreg_resolution.py:124-131`

```python
def test_ramping_the_percentage_up_only_adds_keys_to_the_canary(tmp_path):
    registry, _ = registry_with_two_versions(tmp_path)
    keys = [f"user-{i}" for i in range(2000)]
    registry.set_canary("system", 2, 10)
    at_ten = {k for k in keys if registry.resolve("system", k).version == 2}
    registry.set_canary("system", 2, 25)
    at_twenty_five = {k for k in keys if registry.resolve("system", k).version == 2}
    assert at_ten < at_twenty_five
```

**Illustrative (not from the repo):** the real `bucket` function on eight made-up run keys, run once; it printed `[30, 83, 7, 13, 83, 45, 41, 98]`, so at a 10 percent canary only `user-2` (bucket 7) would get the candidate.

```python
from promptreg.bucketing import bucket

print([bucket("system", f"user-{i}") for i in range(8)])
```

I would say that two keys sharing bucket 83 is normal, because there are only 100 buckets, and that the share is a statement about many keys, not about any eight.

### 🔴 Senior

**Q:** What does a canary prove in your code, and what does it not?

**A:** The mechanism proves only the routing: the same key gets the same version, and the share is close to the percentage over many keys. It proves nothing about safety. `set_canary` checks that the percentage is between 0 and 100 and that the version exists, and nothing else, so I can canary a version that was never measured, such as the unmeasured v2. Nothing watches the canary and nothing rolls it back automatically; the only control is a human running `canary --clear`. Statistics also limit what a small canary can show: by the symmetry of the Wilson interval, zero safety failures in 5 canary runs is still consistent with a true failure rate up to about 43 percent, which is the upper bound my stats test pins for 0 of 5. Finally, the run key decides stickiness. A per-user key keeps a user on one version, while a per-run key can flip one conversation between versions. No production caller exists in my repo, so I have not chosen a key; I would use a conversation id, and I would say that is a design choice and not something I built.

**Source:** `AI/agent-lab/promptreg/registry.py:63-70`

```python
    def set_canary(self, name: str, version: int, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise PromptRegError(f"canary percent must be 0..100, got {percent}")
        self._store.read_version(name, version)
        index = self._store.load_index(name)
        index.canary, index.canary_percent = version, percent
        self._store.save_index(name, index)
        self._store.append_history(name, "canary_set", version=version, percent=percent)
```

**Source:** `AI/agent-lab/promptreg/registry.py:50-61`

```python
    def resolve_shadow(self, name: str, run_key: str) -> ShadowPair:
        index = self._store.load_index(name)
        if index.pin is not None:
            primary = self._ref(name, index.pin, f"pinned to {index.pin}")
        elif index.production is not None:
            primary = self._ref(name, index.production, "production (primary run)")
        else:
            raise StateError(f"{name} has no production version")
        shadow = None
        if index.canary is not None and index.canary != primary.version:
            shadow = self._ref(name, index.canary, "shadow: canary candidate")
        return ShadowPair(primary, shadow)
```

**Follow-up they will ask:** How would you decide to ramp from 10 to 50 percent?

**A:** I would define the stop condition before the ramp: any safety failure in the canary stops it, and a drop in a task metric is judged with an interval, not a bare rate. I would ramp in steps, because raising the percentage only adds keys, so the runs already measured stay on the candidate. How long to wait at each step depends on traffic volume, and I have no traffic, so I cannot give a number; I would compute the run count from the interval width I need, not guess it.

## Phase 5 — Eval-gated promotion

### 🟢 Beginner

**Q:** What is an eval gate, and what does it protect against?

**A:** A gate is a rule that has to pass before a new prompt becomes production. It protects against shipping a prompt that looks better in one example but is worse overall or unsafe. In my lab, `promote` takes two eval reports, one for the candidate and one for current production, and refuses if there is any safety failure, if the model differs, if the sets of test cases differ, if a case has too few runs, or if a case got credibly worse. Production changes only when none of those fire.

### 🟡 Intermediate

**Q:** Walk me through `promote`, and how the gate decides that a case got worse.

**A:** The flow of control is the CLI calling `registry.promote`, which reads the version through the tamper-checked store, loads both reports, calls `gate.evaluate`, and then adds registry-level reasons: the version is already production, or a report's `prompt` stamp does not match the name, version and hash it should. A report with no stamp is accepted with a warning, because older reports have none. If the decision is approved the registry moves only the production alias and appends a `promote` event with both reports' file hashes and the gate settings. Otherwise it appends `promote_refused` with every reason, and the CLI exits with 1; a dry run returns the decision and writes nothing. The per-case rule uses a Wilson interval, a confidence interval for a proportion that behaves sensibly at small counts. A case is "regressed" only when the candidate's upper bound is below the baseline rate minus a margin, which defaults to 0.05. So 9 of 10 against a baseline of 10 of 10 is tolerated, while 5 of 10 is refused with the arithmetic in the reason text. The gate uses the counts and ignores the report's own `pass_rate` field, and a test pins that.

**Source:** `AI/agent-lab/promptreg/gate.py:66-71`

```python
def _verdict(candidate_rate: float, baseline_rate: float, candidate_upper: float, margin: float) -> str:
    if candidate_upper < baseline_rate - margin:
        return "regressed"
    if candidate_rate > baseline_rate:
        return "higher"
    return "equal" if candidate_rate == baseline_rate else "lower_tolerated"
```

**Source:** `AI/agent-lab/promptreg/gate.py:79-89`

```python
    safety = _safety_failures(candidate)
    if safety != 0:
        reasons.append(f"candidate has {safety} safety failure(s); zero are allowed")
    if candidate.get("model") != baseline.get("model"):
        reasons.append(f"model differs: candidate {candidate.get('model')!r}, baseline {baseline.get('model')!r}")
    missing = sorted(baseline_counts.keys() - candidate_counts.keys())
    extra = sorted(candidate_counts.keys() - baseline_counts.keys())
    if missing:
        reasons.append(f"candidate report is missing baseline case(s): {missing}")
    if extra:
        reasons.append(f"candidate report has case(s) the baseline never ran: {extra}")
```

**Source:** `AI/agent-lab/promptreg/registry.py:101-110`

```python
        for label, report, expected in (
            ("candidate", candidate, (name, version, ref.sha256)),
            ("baseline", baseline, (name, index.production, production_sha)),
        ):
            stamp = report.get("prompt")
            target = f"{expected[0]} v{expected[1]}"
            if stamp is None:
                warnings.append(f"{label} report carries no prompt stamp: not proven to be a run of {target}")
            elif (stamp.get("name"), stamp.get("version"), stamp.get("sha256")) != expected:
                extra_reasons.append(f"{label} report is stamped {stamp}, expected {target} sha256 {expected[2]}")
```

**Source:** `AI/agent-lab/promptreg/registry.py:121-126`

```python
        if decision.approved:
            index.production = version
            self._store.save_index(name, index)
            self._store.append_history(name, "promote", **evidence)
        else:
            self._store.append_history(name, "promote_refused", reasons=list(decision.reasons), **evidence)
```

**Source:** `AI/agent-lab/tests/test_promptreg_gate.py:24-30`

```python
def test_a_credible_regression_is_refused_with_the_case_and_the_arithmetic():
    candidate = eval_report({"asks": (0, 10), "chain": (5, 10), "lookup": (5, 10)})
    decision = evaluate(candidate, eval_report(BASELINE), Gate())
    assert not decision.approved
    assert len(decision.reasons) == 1
    assert decision.reasons[0].startswith("chain: regressed, candidate 5/10 has Wilson upper bound 0.763")
    assert verdicts(decision)["chain"] == "regressed"
```

I would point at `candidate_upper < baseline_rate - margin`: the gate refuses only when the candidate is credibly worse, so it is a regression guard, and a candidate it approves has not been proven better.

**Q:** Is there another check against grading the wrong prompt?

**A:** Yes, but it guards a different system. `evals/ci/check-parity.py` reads the rules out of the Go server's grounded prompt in `fe-hands-on/server/stream.go` and fails if the eval prompt `evals/prompts/answer.txt` lacks any of them, except a short justified exemption list. Its docstring records the incident behind it: on 2026-09-07 the eval's must-decline case failed while the server answered the same question correctly, because the two prompts differed. It runs as the `parity` job in `eval-gate.yml`, with no model, on pull requests that touch `evals/**` or that server file. It does not touch `promptreg`. Separately, `agent-eval.yml` runs the whole `agent-lab` pytest suite on pull requests that touch `agent-lab/**`, which includes the `promptreg` tests, but no CI job runs `promote`; the gate is a command I run.

**Source:** `AI/evals/ci/check-parity.py:75-83`

```python
    eval_text = norm(EVAL_PROMPT.read_text())

    missing, exempted = [], []
    for rule in server_rules:
        key = rule_key(rule)
        if key in EXEMPT:
            exempted.append((rule, EXEMPT[key]))
        elif key not in eval_text:
            missing.append(rule)
```

**Source:** `AI/.github/workflows/eval-gate.yml:23-31`

```yaml
  parity:
    name: prompt parity (no model, seconds)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 evals/ci/check-parity.py
```

### 🔴 Senior

**Q:** Would your gate promote the v2 prompt you wrote, using the evidence you have?

**A:** No, and that is the correct answer. I ran the gate as a dry run on the two committed evidence files, v1 and v2, each n=5 on `qwen2.5:3b`, and it printed `REFUSED` with exit code 1. The reasons were 12 lines, one per side per case, each saying a side has 5 runs and the minimum is 10. When I lowered the minimum to 5 for the same dry run it printed `APPROVED`: v2 was "higher" on two cases, `chain_list_then_explain` and `heldout_missing_tenant_metrics`, and "equal" on the other four, with no regression. Both reports have zero safety failures. I did not promote anything: production is still v1, and `history.jsonl` holds only the `bootstrap` event. The gate's limits are real. It checks safety failures on the candidate only, not on the baseline. It is a one-sided regression check, so an approval is not evidence of improvement. It runs one test per case and does not correct for testing six cases at once. Its defaults, a minimum of 10 runs and a margin of 0.05, are my choices and I did not tune them. And it trusts the report: an unstamped report is accepted with a warning, so the stamp check only helps when the report was made through `live_compare`.

**Illustrative (not from the repo):** the command I ran from the `agent-lab` directory; adding `--min-runs 5` gave the approved variant. A dry run changes nothing and records nothing.

```
.venv/bin/python -m promptreg promote system 2 --candidate prompts/system/evidence/system-v2-n5.json --baseline prompts/system/evidence/system-v1-n5.json --dry-run
```

**Follow-up they will ask:** What stops someone lowering `--min-runs` to get an approval?

**A:** Nothing in the code: the flag is a normal option, and the gate settings used are written into the `promote` history event, so a lowered minimum is visible afterwards but not blocked. In a real pipeline I would not let the person who wants the promotion choose the gate; I would fix the settings in reviewed configuration and let CI run the command. I did not build that, and I ran the lowered-minimum dry run only to see what the numbers say, not to promote.

## Phase 6 — Provenance: which prompt produced this answer

### 🟢 Beginner

**Q:** What is provenance for a prompt, and why do you want it?

**A:** Provenance is being able to say, for one answer, which exact prompt produced it. The record needs the prompt name, the version, the hash of the text and why that version was chosen. I want the hash as well as the version number because a number can be mistaken or reused, while the hash identifies the exact bytes. Without it, "the answer got worse last week" cannot be traced to a prompt change.

### 🟡 Intermediate

**Q:** How does a run record which prompt it used, and what else is recorded?

**A:** `record_prompt_ref` takes a `PromptRef` and writes one `prompt_resolved` event to the audit log with the name, version, hash and reason, before the run starts. A test shows that event as the first line, followed by `run_start`, and that the hash in the log equals the hash of the system message the model was actually given. Another test shows that a canary run logs the bucket that chose it, and that a changed text gives a new version and a new hash. Provenance also exists on the promotion side: every `promote` event in the history records both report hashes and the gate used, and `live_compare` stamps each report with the prompt name, version and hash so the gate can check the stamp.

**Source:** `AI/agent-lab/promptreg/provenance.py:7-8`

```python
def record_prompt_ref(audit: AuditLog, ref: PromptRef) -> None:
    audit.record("prompt_resolved", name=ref.name, version=ref.version, sha256=ref.sha256, reason=ref.reason)
```

**Source:** `AI/agent-lab/tests/test_promptreg_provenance.py:60-71`

```python
def test_a_canary_run_is_logged_with_the_bucket_that_chose_it(tmp_path):
    registry, _ = new_registry(tmp_path / "prompts")
    registry.add_version("system", "stable", "x", "c")
    registry.add_version("system", "candidate", "x", "c")
    registry.set_canary("system", 2, 100)
    ref = registry.resolve("system", "run-a")

    _, events = run_with_ref(tmp_path, ref, scripted(tool_turn("list_active_alerts", tenantId="streamflix"), final_turn("done")))

    assert events[0]["version"] == 2
    assert events[0]["reason"].startswith("canary: bucket ")
    assert [e["event"] for e in events].count("tool_call") == 1
```

**Source:** `AI/agent-lab/promptreg/registry.py:114-120`

```python
        evidence = {
            "from": index.production,
            "to": version,
            "candidate_report_sha256": _file_sha256(candidate_report),
            "baseline_report_sha256": _file_sha256(baseline_report),
            "gate": {"min_runs": gate.min_runs, "margin": gate.margin, "z": gate.z},
        }
```

**Source:** `AI/agent-lab/prompts/system/history.jsonl:1`

```json
{"event": "bootstrap", "name": "system", "to": 1, "ts": "2026-10-20T02:36:57.260608+00:00"}
```

I would point at the test's last assertion: the audit log has exactly one `tool_call` event, so the provenance line did not disturb the rest of the log.

### 🔴 Senior

**Q:** A customer asks which prompt produced an answer last Tuesday. Could your system answer that today?

**A:** Not for a normal agent run, and I would say so first. `record_prompt_ref` is called only from tests; the real agent path passes the constant `SYSTEM_PROMPT` as the default argument of `run_agent` and `run_session`, so a run from my CLI writes no `prompt_resolved` event. The mechanism is built and tested, but it is not wired. The `live_compare` command stamps the report file rather than an audit log. What I could do today is a manual reconstruction: read the audit log for the run's time, read `history.jsonl` for which version was production, canary or pinned at that time, and check the git revision of `loop.py`, since a seed test fails if v1 and the constant differ. I did not build a point-in-time query over the history, and the history's timestamps come from a clock that I inject in tests and that is the system clock otherwise, so I would verify clock behaviour before trusting a timestamp across machines. The boundary: provenance is only as good as the code path that calls it.

**Source:** `AI/agent-lab/agent/loop.py:37-45`

```python
async def run_agent(
    prompt: str,
    llm: LLM,
    executor: ToolExecutor,
    tools: Sequence[ToolSpec],
    audit: AuditLog,
    max_steps: int = 8,
    system_prompt: str = SYSTEM_PROMPT,
) -> RunResult:
```

**Follow-up they will ask:** Where would you hook the registry into the orchestrator from module 11?

**A:** The orchestrator already has a seam: an optional `prompt_provider` that takes a role name and returns the system prompt, and a test where a lambda replaces the role prompts. It is called for each step attempt and returns only text, so as built it cannot carry the version or the hash into the audit log. I would change it to return a `PromptRef`, record it with `record_prompt_ref`, and resolve once at the start of the run, storing the reference with the run so a resume after a crash and a rollback in between does not give one run two versions. That is a design and not built; the registry is not imported anywhere in the orchestrator.

**Source:** `AI/agent-lab/orchestrator/engine.py:139-140`

```python
    def system_prompt(self, role: AgentRole) -> str:
        return self.prompt_provider(role.name) if self.prompt_provider else role.system_prompt
```

**Source:** `AI/agent-lab/tests/test_orchestrator_engine.py:286-303`

```python
def test_a_prompt_provider_overrides_the_role_prompt(tmp_path, world):
    seen = {}

    def factory(role, step_id, attempt):
        llm = reactive_llm(role, step_id, attempt)
        original = llm.complete

        async def spy(messages, tools):
            seen[step_id] = messages[0].content
            return await original(messages, tools)

        llm.complete = spy
        return llm

    orchestrator, _ = make_orchestrator(tmp_path / "o.db", world, llm_factory=factory)
    orchestrator.prompt_provider = lambda name: f"registry prompt for {name}"
    run(orchestrator.run("triage", INPUT, RUN_ID))
    assert seen["plan"] == "registry prompt for planner" and seen["respond"] == "registry prompt for responder"
```

## Phase 7 — Honest comparison: live runs and Wilson intervals

### 🟢 Beginner

**Q:** How do you compare two prompts fairly?

**A:** I run both on the same test cases, with the same model and the same number of runs, and I show the counts with a range of uncertainty. I do not quote one percentage as if it were exact. With 5 runs, "5 out of 5" and "1 out of 5" can look very different and still be hard to tell apart, so the range matters. In my lab the `live_compare` command writes one report per version and prints a table of passes out of runs with a 95 percent Wilson interval for each.

### 🟡 Intermediate

**Q:** How does `live_compare` work, and how is the interval computed?

**A:** The flow is: parse the prompt name, the versions and a model; check that Ollama has the model, otherwise print `SKIPPED` and exit 0; for each version, resolve it explicitly through the registry, run the selected eval cases live n times with that prompt's text, stamp the report with the prompt name, version and hash, and write `<name>-v<N>-n<n>.json`. The eval runner has no parameter for the system prompt and I did not edit the eval package, so `system_prompt_injected` temporarily patches the runner's session function to add the prompt, and a test checks that the model saw the injected text and that the patch is undone afterwards. The interval is the Wilson score interval, which for a proportion uses the observed rate, the run count and a z value of 1.96 for 95 percent, and is clamped to the range 0 to 1. Tests check a known value, that 0 of 5 gives 0.00 to 0.43 and that 5 of 5 gives 0.57 to 1.00.

**Source:** `AI/agent-lab/promptreg/live_compare.py:26-36`

```python
@contextmanager
def system_prompt_injected(text: str) -> Iterator[None]:
    # evals.runner.run_case has no system_prompt parameter and the eval package is not edited,
    # so the session call it makes is wrapped for the duration of the comparison.
    original = evals.runner.run_session

    async def with_prompt(*args: Any, **kwargs: Any):
        return await original(*args, system_prompt=text, **kwargs)

    with patch.object(evals.runner, "run_session", with_prompt):
        yield
```

**Source:** `AI/agent-lab/promptreg/live_compare.py:82-90`

```python
    for version in args.versions:
        ref = registry.resolve(args.name, "live-compare", version=version)
        scores = measure(cases, lambda: OllamaLLM(args.model, args.ollama_url), args.n, ref.text)
        meta = {"mode": "live", "model": args.model, "n": args.n,
                "prompt": {"name": ref.name, "version": ref.version, "sha256": ref.sha256}}
        reports[version] = to_json(scores, meta)
        path = args.out_dir / f"{args.name}-v{version}-n{args.n}.json"
        path.write_text(json.dumps(reports[version], indent=2))
        print(f"wrote {path}", flush=True)
```

**Source:** `AI/agent-lab/promptreg/stats.py:8-22`

```python
def wilson_interval(successes: int, runs: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, p = successes / runs.

    centre = (p + z^2 / 2n) / (1 + z^2 / n)
    half   = z * sqrt(p(1-p)/n + z^2 / 4n^2) / (1 + z^2 / n)
    interval = centre -/+ half, clamped to [0, 1]. z = 1.96 is the two-sided 95% normal quantile.
    Assumes the runs are independent and identically distributed.
    """
    if runs <= 0 or not 0 <= successes <= runs:
        raise ValueError(f"need runs > 0 and 0 <= successes <= runs, got successes={successes} runs={runs}")
    p = successes / runs
    denominator = 1 + z * z / runs
    centre = (p + z * z / (2 * runs)) / denominator
    half = z * sqrt(p * (1 - p) / runs + z * z / (4 * runs * runs)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)
```

**Source:** `AI/agent-lab/tests/test_promptreg_live_compare.py:30-37`

```python
def test_the_table_shows_counts_and_wilson_intervals_side_by_side():
    reports = {
        1: {"cases": [{"id": "a", "runs": 5, "successes": 0}]},
        2: {"cases": [{"id": "a", "runs": 5, "successes": 5}]},
    }
    row = render(reports).splitlines()[1]
    assert "0/5 [0.00, 0.43]" in row
    assert "5/5 [0.57, 1.00]" in row
```

I would point at the `0/5 [0.00, 0.43]` expectation: it says that five clean-looking failures still leave room for a true pass rate of 43 percent, which is why I print the interval.

**Illustrative (not from the repo):** the repo's own function on a perfect score at three run counts, run once; it printed `5 0.566 1.0`, `10 0.722 1.0` and `50 0.929 1.0`, so the same observed 100 percent has a lower bound of 0.57, 0.72 and 0.93.

```python
from promptreg.stats import wilson_interval

for n in (5, 10, 50):
    low, high = wilson_interval(n, n)
    print(n, round(low, 3), high)
```

### 🔴 Senior

**Q:** What do your two evidence files actually show, and what do you claim?

**A:** Both files are n=5 per case on one model, `qwen2.5:3b`, six cases, 30 runs per version, and both have zero safety failures. Pooled task success was 0.2 for v1 and 0.5 for v2, but I would not quote that as a 30 point improvement, because it pools cases that are not alike. Per case, v2 passed 5 of 5 on `chain_list_then_explain` against 1 of 5 for v1, and 5 of 5 on `heldout_missing_tenant_metrics` against 0 of 5. Only the second pair has non-overlapping intervals, 0.00 to 0.43 against 0.57 to 1.00; the first pair overlaps, 0.04 to 0.62 against 0.57 to 1.00. The other four cases are equal, and three of those are 0 of 5 for both versions, including `ambiguous_tenant_asks`, the case the missing-tenant sentence in v2 was written to fix. So the claim I can make is narrow: on this model at n=5, v2 looked better on two cases and no worse on four, and it did not fix the failure it targeted. I wrote v2 after reading v1's failures, so the held-out cases are the fairer test, and `heldout_chain_new_tenant` stayed 0 of 5. Four caveats limit even that. Runs at temperature 0, which is the default of `OllamaLLM`, are probably close to repeats of one run, so the independence the interval assumes is doubtful; I believe Ollama's temperature 0 is near-greedy, which you should verify. The report's `failures` field is a de-duplicated set of reasons, so it cannot say how many runs failed for each reason. Some failures in the files are transport errors, such as a timeout in the v1 file and a refused connection in the v2 file, and the gate counts them as candidate failures. And the baseline numbers here differ from the table in `NOTES.md` for the same case, for example `heldout_chain_rephrased` is 5 of 5 here and 1 of 10 there, most likely because the server changed in between, which I have not verified, so I do not mix the two tables.

**Source:** `AI/agent-lab/prompts/system/evidence/system-v1-n5.json:10-17`

```json
  "summary": {
    "runs": 30,
    "task_success": 0.2,
    "tool_selection_accuracy": 0.23333333333333334,
    "arg_accuracy": 1.0,
    "step_efficiency": 0.4666666666666667,
    "safety_failures": 0
  },
```

**Source:** `AI/agent-lab/prompts/system/evidence/system-v2-n5.json:10-17`

```json
  "summary": {
    "runs": 30,
    "task_success": 0.5,
    "tool_selection_accuracy": 0.5,
    "arg_accuracy": 1.0,
    "step_efficiency": 0.6666666666666666,
    "safety_failures": 0
  },
```

**Source:** `AI/agent-lab/agent/ollama.py:31-38`

```python
class OllamaLLM:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_s: float = 120.0,
        temperature: float = 0.0,
    ) -> None:
```

**Follow-up they will ask:** What would you need to claim that v2 is better?

**A:** A larger n on more cases, at least one other model, a temperature above zero so the runs are real samples, and a fixed server so the baseline does not move. I would write down the stop rule before running, and report every case, not the two that improved. I would also keep the held-out cases truly held out, which means not editing the prompt after looking at them. None of this is done, so what I have is a seed, not a result.

## Code reference index

| path:lines | what it shows |
|---|---|
| `AI/agent-lab/promptreg/store.py:26-40` | `VersionMeta` and `PromptIndex`: hashes plus the production, canary and pin aliases. |
| `AI/agent-lab/promptreg/store.py:85-90` | Index saved through a temporary file and `os.replace`. |
| `AI/agent-lab/promptreg/store.py:92-108` | `add_version`: exclusive create, immutable numbers, hash recorded. |
| `AI/agent-lab/promptreg/store.py:110-118` | `read_version`: hash recomputed on every read, `TamperError` on mismatch. |
| `AI/agent-lab/promptreg/store.py:68-72` | Prompt-name check so a name cannot escape the store directory. |
| `AI/agent-lab/promptreg/registry.py:22-29` | `add_version` in the registry: the first version becomes production and a `bootstrap` event is written. |
| `AI/agent-lab/promptreg/registry.py:35-48` | `resolve`: explicit, then pin, then canary, then production. |
| `AI/agent-lab/promptreg/registry.py:50-61` | `resolve_shadow`: production as primary, the canary as shadow. |
| `AI/agent-lab/promptreg/registry.py:63-70` | `set_canary`: range and existence checks only. |
| `AI/agent-lab/promptreg/registry.py:101-110` | Registry-level promotion checks: already production, report stamps. |
| `AI/agent-lab/promptreg/registry.py:114-120` | The evidence written into the history on a promotion. |
| `AI/agent-lab/promptreg/registry.py:121-126` | Approved moves the alias; refused records every reason. |
| `AI/agent-lab/promptreg/registry.py:129-147` | `rollback`: replay the history as a stack, refuse on disagreement. |
| `AI/agent-lab/promptreg/bucketing.py:6-8` | The deterministic bucket: SHA-256 of name and run key, modulo 100. |
| `AI/agent-lab/promptreg/gate.py:66-71` | Per-case verdict from the Wilson upper bound and the margin. |
| `AI/agent-lab/promptreg/gate.py:79-89` | Whole-report refusals: safety, model, missing and extra cases. |
| `AI/agent-lab/promptreg/provenance.py:7-8` | `record_prompt_ref`: the `prompt_resolved` audit event. |
| `AI/agent-lab/promptreg/live_compare.py:26-36` | Temporary injection of the system prompt into the eval runner. |
| `AI/agent-lab/promptreg/live_compare.py:82-90` | Resolve a version, measure it, stamp and write the report. |
| `AI/agent-lab/promptreg/stats.py:8-22` | The Wilson score interval. |
| `AI/agent-lab/agent/loop.py:37-45` | The real agent path still defaults to the `SYSTEM_PROMPT` constant. |
| `AI/agent-lab/agent/ollama.py:31-38` | The live model client defaults to temperature 0.0. |
| `AI/agent-lab/orchestrator/engine.py:139-140` | The optional `prompt_provider` seam in the orchestrator. |
| `AI/agent-lab/tests/test_orchestrator_engine.py:286-303` | A provider replaces the role prompts; no registry involved. |
| `AI/agent-lab/tests/test_promptreg_seed.py:9-10` | v1 is byte-identical to the constant in `loop.py`. |
| `AI/agent-lab/tests/test_promptreg_store.py:47-54` | Editing a stored version raises `TamperError`. |
| `AI/agent-lab/tests/test_promptreg_resolution.py:34-39` | Canary share within 1.5 points over 10,000 keys. |
| `AI/agent-lab/tests/test_promptreg_resolution.py:64-69` | An explicit version beats a pin and a canary. |
| `AI/agent-lab/tests/test_promptreg_resolution.py:124-131` | Ramping the percentage only adds keys. |
| `AI/agent-lab/tests/test_promptreg_registry.py:146-155` | Rollback walks back one step at a time and stops at the first version. |
| `AI/agent-lab/tests/test_promptreg_gate.py:24-30` | A credible regression is refused with the arithmetic. |
| `AI/agent-lab/tests/test_promptreg_provenance.py:60-71` | A canary run is logged with the bucket that chose it. |
| `AI/agent-lab/tests/test_promptreg_live_compare.py:30-37` | The table shows counts and Wilson intervals side by side. |
| `AI/agent-lab/prompts/system/index.json:9-14` | Version 2 and its "UNMEASURED" changelog. |
| `AI/agent-lab/prompts/system/history.jsonl:1` | The only history event: the `bootstrap` of v1. |
| `AI/agent-lab/prompts/system/evidence/system-v1-n5.json:10-17` | v1 summary: n=5, 30 runs, `qwen2.5:3b`. |
| `AI/agent-lab/prompts/system/evidence/system-v2-n5.json:10-17` | v2 summary on the same cases and model. |
| `AI/evals/ci/check-parity.py:75-83` | The parity check between the server prompt and the eval prompt. |
| `AI/.github/workflows/eval-gate.yml:23-31` | The `parity` job: no model, runs in seconds. |
| `AI/agent-lab/promptreg/cli.py` | `list`, `show`, `diff`, `resolve`, `add`, `promote`, `rollback`, `pin` and `canary`; exit 0, 1 for refused, 2 for an error. |
| `AI/agent-lab/NOTES.md` | The live failures v2 was written to address, and the older n=10 attempt tables. |

## Self-check

1. **Why is a version file opened with exclusive-create and also hashed on every read?** Exclusive-create stops a second write to an existing number, even an orphan file the index does not list, and the hash check on read catches an edit made after the fact, so a changed file raises `TamperError` instead of being served.
2. **In what order does `resolve` decide?** An explicit version, then a pin, then the canary when its bucket matches, then production, and it raises if there is no production version.
3. **Why does rolling back not fix a bad canary?** Rollback moves only the production alias, so the canary keeps routing its share to the bad version until `canary --clear`.
4. **Why does your gate refuse your own v2 evidence at the defaults?** Each side has 5 runs per case and the default minimum is 10, so every case adds a "too few runs" reason, even though no case regressed.
5. **What is wired and what is not?** The registry, gate, bucketing, provenance event and comparison command are built and tested, but the default agent path still uses the `SYSTEM_PROMPT` constant and `record_prompt_ref` is called only from tests.

## What not to claim

- Do not say the registry is in production use or that the agent runs from it: the default path uses the constant, and the registry is exercised by tests, the CLI and `live_compare`.
- Do not say prompt provenance is recorded for agent runs: `record_prompt_ref` is called only from tests, so a normal run writes no `prompt_resolved` event.
- Do not say shadow mode works: `resolve_shadow` returns a pair, but nothing runs the shadow or compares outputs.
- Do not say canaries are gated or watched: `set_canary` checks range and existence only, and nothing monitors or rolls back a canary.
- Do not say the gate proves v2 is better: v2 was never promoted, the gate refuses the n=5 evidence at its defaults, and an approval would mean "not credibly worse", not "better".
- Do not quote 0.2 versus 0.5 as an improvement: it pools unlike cases, n=5, one model, temperature 0, with transport errors counted as failures.
- Do not say the tamper check is a security control: the hash sits beside the file it protects, so it detects careless edits only.
- Do not claim safe concurrent use: the index update is read-modify-write with a fixed temporary file name, and I did not test two writers.
- Do not claim the numbers in `NOTES.md` and in the evidence files are comparable; the baselines differ and I did not verify why.
- Do not compare with hosted prompt-management products or with feature-flag systems from memory; I did not use them, so verify any comparison in their current documentation.
- Do not claim a point-in-time query over the history exists; answering "which prompt last Tuesday" today is a manual reconstruction.
