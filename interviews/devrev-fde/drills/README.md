# DevRev FDE coding drills

Nine drills, each implemented twice (TypeScript, Python) with the same API shape and the same tests. Read [DRILLS.md](DRILLS.md) for the problem statements, the "say this" scripts, pitfalls and follow-ups.

Pinned versions actually installed and run: Node 24.6.0, npm 11.5.1, TypeScript 7.0.2, Vitest 5.0.5, @types/node 24.19.2, Python 3.14.7, pytest 9.1.1. No global installs; Python is stdlib only.

## TypeScript (ESM, strict, Vitest)

```
cd interviews/devrev-fde/drills/ts
```

```
npm ci
```

```
npx vitest run
```

```
npx tsc --noEmit
```

Run one drill's tests while practising:

```
npx vitest run test/retry.test.ts
```

## Python (venv, pytest)

```
cd interviews/devrev-fde/drills/py
```

```
python3.14 -m venv .venv
```

```
.venv/bin/pip install --group dev
```

```
.venv/bin/pytest -q
```

Run one drill's tests while practising:

```
.venv/bin/pytest -q tests/test_retry.py
```

## Layout

```
drills/
  DRILLS.md        statements, scripts, pitfalls, follow-ups
  ts/src, ts/test  one file per drill, one test file per drill
  py/fde, py/tests same names in snake_case
```

## Notes

- If `npx vitest run` fails with "Cannot find native binding" (an npm optional-dependency bug that hit during the first install here), delete `node_modules` and re-run `npm ci`.
- The TS sources use only erasable syntax, so Node 24 can run a drill file directly without a build step, for example `node src/lru.ts` from `ts/` after adding a few lines at the bottom.
- Python drills are synchronous on purpose (stdlib only, whiteboard-friendly); the TS retry and extractor are async because their I/O is. Converting the Python ones to `async def` is mechanical.
