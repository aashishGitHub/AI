# 02 · TypeScript for Real Codebases
> Make the compiler do the work: assertion-free narrowing, generics that infer, type-level utilities, React component typing and runtime trust boundaries · 7 questions · ~1 h 44 min
Source: https://whetstone-v1.vercel.app/#typescript

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | Model your data so you never need as: unions, narrowing, type guards and satisfies | Senior | 15 min | narrowing · type guards · satisfies | [notes](01-never-need-as-narrowing-satisfies.md) |
| 02 | Write generic functions whose types infer correctly: constraints, const type parameters and NoInfer | Senior | 15 min | generics · inference · const type parameters | [notes](02-generics-that-infer-noinfer-const.md) |
| 03 | Conditional types, infer and mapped types: build DeepReadonly, PathValue and a typed event map | Lead / Staff | 20 min | conditional types · infer · mapped types | [notes](03-conditional-mapped-types-pathvalue.md) |
| 04 | Type a UI state machine with discriminated unions and exhaustive checks | Senior | 12 min | discriminated unions · never · reducers | [notes](04-typed-ui-state-machine.md) |
| 05 | Type React components well: polymorphic as props, generic components and forwarding props | Lead / Staff | 18 min | react · typescript · polymorphic components | [notes](05-typing-react-polymorphic-generic.md) |
| 06 | Types vanish at runtime. Where do you validate data, and how do you share types with the backend? | Lead / Staff | 12 min | zod · validation · openapi | [notes](06-runtime-validation-shared-types.md) |
| 07 | Where is TypeScript unsound, and how do you defend against it? | Principal | 12 min | soundness · variance · any | [notes](07-typescript-unsoundness-defenses.md) |

## How these connect
- **Make illegal states unrepresentable (01, 04)**: discriminated unions + `never` exhaustiveness are the same idea applied to data (01) and to transitions (04). Study together.
- **Inference design (02, 03, 05)**: 02 is the call-site ergonomics of generics; 03 is the type-level toolkit library authors use; 05 applies both to design-system components. Do 02 before 03.
- **The type/runtime gap (06, 07)**: 07 lists where the compiler lies; 06 is the architectural answer (validate at trust boundaries, single source of truth for schema and type). 01's "a type predicate is a trusted claim" is the bridge.
- Principal-level thread across 03 and 07: type cleverness and strict flags have cost (compile time, migration effort); talk about containment and ratchets, not just syntax.
- Suggested order: 01 → 04 → 02 → 05 → 03 → 06 → 07.
