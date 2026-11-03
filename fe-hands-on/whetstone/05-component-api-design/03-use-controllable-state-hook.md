# Support controlled and uncontrolled usage with one useControllableState hook
**Round:** 05 · Component API Design · **Level:** Senior · **Time:** 12 min · **Tags:** controlled components · uncontrolled · hooks
Source: https://whetstone-v1.vercel.app/#component-api-design

## What they're really testing
Write `useControllableState({ value, defaultValue, onChange })` so one component behaves like a native input in both modes.

Tests from the prompt: uncontrolled starts at `defaultValue`, updates itself, calls `onChange`; controlled ignores internal updates but still calls `onChange` with the requested value; switching modes warns in dev; functional updater `setValue(v => v + 1)` works in both modes without staleness.

## Core answer (key points)
- **Mode detection:** `value !== undefined` → controlled. Use `undefined`, not falsy, so `null`/`''`/`0` are valid controlled values.
- **Source of truth:** controlled → parent's `value`; uncontrolled → internal `useState(defaultValue)`.
- **`setValue(next)`:** resolve functional updaters against the *latest* value (ref, not render closure), skip if `Object.is` equal, update internal state only if uncontrolled, always call `onChange`.
- **Stable setter:** keep `onChange` and current value in refs so `setValue` identity doesn't change every render (safe in deps, memo-friendly).
- **Dev warning** when a component flips between modes, like React's input warning.
- **Reset** an uncontrolled instance with `key`, not a `reset` prop.

## Mental model / flow
| `value` passed? | Truth | `setValue(x)` |
|---|---|---|
| no | internal state | set internal + `onChange(x)` |
| yes | parent prop | `onChange(x)` only; UI moves when parent re-renders |

## Code sketch
```ts
type Updater<T> = T | ((prev: T) => T);

export function useControllableState<T>({ value, defaultValue, onChange }: {
  value?: T; defaultValue: T; onChange?: (v: T) => void;
}) {
  const [inner, setInner] = useState(defaultValue);
  const controlled = value !== undefined;
  const current = controlled ? (value as T) : inner;

  const latest = useRef(current);
  const cb = useRef(onChange);
  useLayoutEffect(() => { latest.current = current; cb.current = onChange; });

  const modeRef = useRef(controlled);
  if (process.env.NODE_ENV !== 'production' && modeRef.current !== controlled) {
    console.warn(`Component switched from ${modeRef.current ? 'controlled' : 'uncontrolled'} to ${controlled ? 'controlled' : 'uncontrolled'}.`);
    modeRef.current = controlled;
  }

  const setValue = useCallback((u: Updater<T>) => {
    const next = typeof u === 'function' ? (u as (p: T) => T)(latest.current) : u;
    if (Object.is(next, latest.current)) return;
    latest.current = next;              // two calls in one tick chain correctly
    if (!controlled) setInner(next);
    cb.current?.(next);
  }, [controlled]);

  return [current, setValue] as const;
}
```
Tests I'd write (Testing Library + a tiny `Counter` using the hook):
```tsx
test('controlled ignores internal updates', async () => {
  const onChange = vi.fn();
  render(<Counter value={1} onChange={onChange} />);
  await user.click(screen.getByRole('button', { name: /inc/i }));
  expect(screen.getByText('1')).toBeInTheDocument();
  expect(onChange).toHaveBeenCalledWith(2);
});
```

## Trade-offs & pitfalls
- `T` that legitimately includes `undefined` can't use this detection; use a separate `controlled` flag or `null`.
- Writing `latest.current` during render instead of in an effect is technically impure; the layout-effect version is safer under concurrent rendering (and with the React Compiler). Writing `latest.current = next` inside the setter is fine.
- Controlled mode with a parent that ignores `onChange` = "frozen" input: by design, but document it.
- `onChange` in controlled mode fires with the *requested* value; parent may reject/transform it.
- Big forms: uncontrolled + FormData/react-hook-form re-render less; controlled wins for live formatting/validation.

## Likely follow-ups
- **Why not `useEffect` to sync prop → state?** Extra render, stale frame, and two sources of truth.
- **Where's this pattern in the wild?** Radix ships a `useControllableState` internally; React's own inputs follow the same contract.
- **Should `onChange` fire on initial mount?** No; only on user-requested change.
- **How to handle `onChange` throwing?** Let it propagate; it's the consumer's bug.

## Say it in 60 seconds
The hook picks its mode from whether `value` is `undefined`. Uncontrolled, it keeps internal state seeded from `defaultValue`; controlled, the parent's `value` is the truth. `setValue` resolves functional updaters against a ref holding the latest value so it's never stale, bails out if nothing changed, updates internal state only when uncontrolled, and always calls `onChange`. I keep `onChange` in a ref so the setter is stable, and warn in dev if a component switches modes. Using `undefined` as the signal keeps `null` available as a controlled empty value, and resets for uncontrolled usage happen with a `key`.
