# Types vanish at runtime. Where do you validate data, and how do you share types with the backend?
**Round:** 02 · TypeScript for Real Codebases · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** zod · validation · openapi
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
Scenario: backend renamed a field, the app crashed for users with old `localStorage` data, yet everything type-checked. Can you name the trust boundaries, set a per-boundary failure policy, and keep runtime checks and types from drifting.

## Core answer (key points)
- Types are erased; they describe what you *believe*, not what arrives.
- **Validate at trust boundaries, trust types inside**: API responses, `localStorage`/IndexedDB, URL/search params, `postMessage`, feature flags/remote config, form input, LLM output.
- **Single source of truth** so check and type can't drift:
  - schema-first (zod/valibot), type via `z.infer`; or
  - contract-first codegen (OpenAPI → openapi-typescript/Orval/Kubb, GraphQL codegen, protobuf).
- "**Parse, don't validate**": convert `unknown` into a typed value once at the edge; downstream code never re-checks.
- Decide **per boundary** whether failure throws, degrades, or reports.
- **Version stored data** and migrate on read; this is what would have prevented the localStorage crash.

## Mental model / flow
```
network / storage / URL / postMessage / LLM
          │ unknown
          ▼
   schema.safeParse ── fail ──► policy: throw | drop item | default | retry  + report contract violation
          │ ok
          ▼
   typed domain value ──► app (no further checks)
```

| Boundary | Policy |
|---|---|
| auth, payments | strict, fail loudly |
| large feeds/lists | validate per item, drop/flag bad ones, keep page usable |
| local storage | validate, migrate by version, fall back to defaults |
| URL params | parse with defaults; never use for authorization |
| `postMessage` | check `event.origin` first, then shape |
| LLM structured output | validate, retry with the error message, then fall back |

## Code sketch
```ts
import { z } from 'zod';

const PrefsV1 = z.object({ v: z.literal(1), theme: z.enum(['light', 'dark']) });
const PrefsV2 = z.object({ v: z.literal(2), colorScheme: z.enum(['light', 'dark', 'system']) });
type Prefs = z.infer<typeof PrefsV2>;
const DEFAULT_PREFS: Prefs = { v: 2, colorScheme: 'system' };

export function readPrefs(raw: string | null): Prefs {
  if (!raw) return DEFAULT_PREFS;
  let json: unknown;
  try { json = JSON.parse(raw); } catch { return DEFAULT_PREFS; }

  const v2 = PrefsV2.safeParse(json);
  if (v2.success) return v2.data;
  const v1 = PrefsV1.safeParse(json);
  if (v1.success) return { v: 2, colorScheme: v1.data.theme };
  report('prefs.contract_violation', v2.error);
  return DEFAULT_PREFS;
}

const Order = z.object({ id: z.string(), total: z.number(), placedAt: z.coerce.date() });
export async function getOrder(id: string, signal?: AbortSignal) {
  const res = await fetch(`/api/orders/${encodeURIComponent(id)}`, { signal });
  if (!res.ok) throw new HttpError(res.status);
  const parsed = Order.safeParse(await res.json());
  if (!parsed.success) {
    report('GET /api/orders/:id', parsed.error);
    throw new ContractError('order payload mismatch');
  }
  return parsed.data;
}
```

## Trade-offs & pitfalls
- **Cost**: heavy schemas on big payloads burn main-thread ms. Validate once at the edge (never in selectors/render), keep schemas lean, consider sampling in production for non-critical lists.
- Codegen trusts the spec; if the backend drifts from its own spec, add response validation in dev/test (or generate zod from OpenAPI).
- **tRPC / shared TS monorepo**: zero codegen, end-to-end types, but couples deploys and is TS-to-TS only.
- GraphQL codegen gives types **per operation**, matching what each screen fetches, better than per-entity types.
- Bundle size of the validation lib matters; valibot is designed to be tree-shakeable (verify current size numbers yourself).

## Likely follow-ups
- **Isn't this duplicating backend validation?** Backend validates input for security; frontend validates output for robustness. Contract-violation reports are often the first alert that a deploy broke a client.
- **How do you evolve APIs without breaking old clients?** Additive changes, tolerant readers (ignore unknown fields, default missing optional ones), versioning or flags for breaking changes, and long-lived clients (mobile, cached SPAs) in mind.
- **Where does validation live in the architecture?** In the API client / repository layer, so components and stores only see domain types.
- **What about forms?** Same schema drives client validation and the submit payload type; server still re-validates.

## Say it in 60 seconds
TypeScript types are erased, so they only describe what I believe arrives. I validate at trust boundaries: API responses, local storage, URL params, postMessage, remote config and LLM output, and I trust the types everywhere inside. To stop the check and the type drifting, there's one source of truth: a zod or valibot schema with the type inferred from it, or a client generated from the backend's OpenAPI or GraphQL contract, ideally with runtime validation in dev and test. Each boundary gets a failure policy: payments fail loudly, feeds drop bad items, storage migrates by version and falls back to defaults. The localStorage crash in the question is exactly what a versioned, validated read would have prevented, and reporting contract violations to monitoring turns a silent break into an alert.
