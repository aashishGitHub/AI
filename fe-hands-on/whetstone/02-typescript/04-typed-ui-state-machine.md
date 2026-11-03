# Type a UI state machine with discriminated unions and exhaustive checks
**Round:** 02 · TypeScript for Real Codebases · **Level:** Senior · **Time:** 12 min · **Tags:** discriminated unions · never · reducers
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
Modelling a checkout flow (cart → address → payment → confirming → success | failed) so "we forgot to handle X" becomes a compile error and invalid transitions are no-ops. The site offers React, Angular and Vue variants; notes below use React `useReducer`.

Test cases given: `PAY` while in `cart` returns the same state, never `payment`; adding `refunding` breaks compilation until handled; `state.error` only accessible after narrowing to `failed`.

## Core answer (key points)
- One object type per state, with a **literal `status` tag** and only the fields valid there.
- Events are a discriminated union on `type`.
- Reducer switches on event, guards on current state, **returns the same state for invalid transitions** (or a typed error), and ends in `assertNever` so new events/states are compile errors.
- Rendering switches on `state.status` with `assertNever` too, so a new state breaks every view that ignores it.
- Late/async events (progress after cancel) are ignored by construction: a classic race fixed by the types.

## Mental model / flow
```
cart ──NEXT──► address ──NEXT──► payment ──PAY──► confirming ──OK──► success
                                     ▲                  └──FAIL──► failed ──RETRY──┘
any ──RESET──► cart
```

## Code sketch
```ts
type Address = { line1: string; zip: string };
type Checkout =
  | { status: 'cart'; items: string[] }
  | { status: 'address'; items: string[] }
  | { status: 'payment'; items: string[]; address: Address }
  | { status: 'confirming'; items: string[]; address: Address; intentId: string }
  | { status: 'success'; orderId: string }
  | { status: 'failed'; items: string[]; address: Address; error: string };

type Ev =
  | { type: 'TO_ADDRESS' }
  | { type: 'SET_ADDRESS'; address: Address }
  | { type: 'PAY'; intentId: string }
  | { type: 'CONFIRMED'; orderId: string }
  | { type: 'DECLINED'; error: string }
  | { type: 'RETRY' };

const assertNever = (x: never): never => { throw new Error(`Unhandled: ${JSON.stringify(x)}`); };

function checkout(s: Checkout, e: Ev): Checkout {
  switch (e.type) {
    case 'TO_ADDRESS':
      return s.status === 'cart' ? { status: 'address', items: s.items } : s;
    case 'SET_ADDRESS':
      return s.status === 'address' ? { status: 'payment', items: s.items, address: e.address } : s;
    case 'PAY':
      return s.status === 'payment' ? { ...s, status: 'confirming', intentId: e.intentId } : s;
    case 'CONFIRMED':
      return s.status === 'confirming' ? { status: 'success', orderId: e.orderId } : s;
    case 'DECLINED':
      return s.status === 'confirming'
        ? { status: 'failed', items: s.items, address: s.address, error: e.error } : s;
    case 'RETRY':
      return s.status === 'failed' ? { status: 'payment', items: s.items, address: s.address } : s;
    default:
      return assertNever(e);
  }
}
```
`{ ...s, status: 'confirming', intentId }` from `payment` type-checks because the spread carries exactly the fields `confirming` needs.

## Trade-offs & pitfalls
- Non-serialisable values (an `AbortController`, a `File`) in state are fine for local `useReducer`, but break Redux's serialisability; keep them in a ref or a side map keyed by id.
- `default: return s` without `assertNever` silently swallows new events; always use `never`.
- Lookup-object alternative: `Record<Checkout['status'], Renderer>` gets exhaustiveness via the key type, but you lose per-branch narrowing unless you use a mapped type over the union.
- Hand-written reducers stop scaling with **parallel states**, hierarchy, delayed transitions or a need to visualise the machine for product/QA. That's when XState/statecharts pay off.

## Likely follow-ups
- **How do you test it?** Pure function: table-driven `(state, event) → state`, including every invalid transition returning the same reference.
- **Invalid transition: same state or error?** Same state for UI resilience (double clicks, late events); log or return a typed `{ ok: false }` if callers need to know.
- **How do you prevent double submit on PAY?** Only `payment` accepts `PAY`; `confirming` ignores it. The button disables from `status`, not a separate boolean.
- **Angular/Vue?** Same union and reducer; drive it from a signal/store (Angular signals, Pinia/ref in Vue) and switch in the template.

## Say it in 60 seconds
I give each state its own object type with a literal status and only the fields valid there, so `error` only exists on `failed` and an order id only on `success`. Events are a union too. The reducer switches on the event, checks the current state, and returns the same state for anything invalid, so a PAY in the cart or a late progress event after cancel is a no-op by construction. Both the reducer and the view end in `assertNever`, which means adding a `refunding` state fails compilation everywhere it isn't handled. The reducer is pure, so I test it table-driven. When I need parallel or nested states, timers, or a diagram to share with product, I move to a statechart library like XState.
