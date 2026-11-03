# Build an OTP input: paste, backspace, autofill and accessibility
**Round:** 06 · Machine Coding · **Level:** Senior · **Time:** 25 min · **Tags:** otp · inputs · paste
Source: https://whetstone-v1.vercel.app/#machine-coding

## What they're really testing
A 6-box one-time-code input that behaves like one field: typing, deleting, pasting and mobile SMS autofill all work, and it's accessible.

Tests: type 1,2,3 → three boxes filled, focus on 4th; Backspace on empty box → move left and clear it; paste `123456` → all filled, `onComplete('123456')` once; paste `12ab56` → digits only; letters ignored; screen reader announces "Digit 3 of 6".

## Core answer (key points)
- **One source of truth:** a single string `value` (contiguous, no holes), rendered across N inputs. Controlled from the parent (`value`/`onChange`) or via a controllable-state hook.
- **Write path:** strip non-digits → splice into value at index → clamp to N → move focus to next empty. Same function handles typing, paste and autofill.
- **Backspace:** box has a digit → clear it; empty → move left and clear that one. Arrow keys move focus; Home/End optional.
- **Paste:** handle `onPaste` on any box, `preventDefault`, write the whole clipboard text from that index.
- **SMS autofill:** `autocomplete="one-time-code"` on the first box (iOS/Android drop the full code into one input) and allow that box to accept N chars.
- **`onComplete` once:** fire only on the transition from incomplete → complete (track previous completeness in a ref), not on every render while full; guard against double submit.
- **A11y:** `role="group"` + `aria-labelledby` for "Verification code"; per-box `aria-label="Digit 3 of 6"`; `inputMode="numeric"` (not `type=number`: spinners, leading-zero loss).
- **Strong alternative:** a *single* input styled to look like boxes (CSS letter-spacing/background). Native paste, autofill, undo, IME and AT just work. Recommend it if design allows.

## Mental model / flow
```
value "12"   boxes [1][2][ ][ ][ ][ ]   focus → 2
type "3" at 2 → "123"                    focus → 3
paste "4 5-6" at 3 → digits "456" → "123456" → complete → onComplete once
Backspace at 5 (filled) → "12345"        focus stays 5
Backspace at 5 (empty)  → "1234"         focus → 4
```

## Code sketch
```tsx
export function OtpField({ length = 6, value, onChange, onComplete }: {
  length?: number; value: string; onChange: (v: string) => void; onComplete?: (v: string) => void;
}) {
  const boxes = useRef<Array<HTMLInputElement | null>>([]);
  const labelId = useId();
  const wasComplete = useRef(false);

  const focus = (i: number) => boxes.current[Math.min(Math.max(i, 0), length - 1)]?.focus();

  const update = (next: string) => {
    const v = next.replace(/\D/g, '').slice(0, length);
    onChange(v);
    const complete = v.length === length;
    if (complete && !wasComplete.current) onComplete?.(v);
    wasComplete.current = complete;
  };

  const insert = (at: number, text: string) => {
    const digits = text.replace(/\D/g, '');
    if (!digits) return;
    const i = Math.min(at, value.length);
    update(value.slice(0, i) + digits + value.slice(i + digits.length));
    focus(i + digits.length);
  };

  const onKey = (i: number) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault();
      if (value[i]) update(value.slice(0, i) + value.slice(i + 1));
      else if (i > 0) { update(value.slice(0, i - 1) + value.slice(i)); focus(i - 1); }
    } else if (e.key === 'ArrowLeft') { e.preventDefault(); focus(i - 1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); focus(i + 1); }
  };

  return (
    <div role="group" aria-labelledby={labelId} className="otp">
      <span id={labelId}>Verification code</span>
      {Array.from({ length }, (_, i) => (
        <input key={i} ref={el => { boxes.current[i] = el; }}
          aria-label={`Digit ${i + 1} of ${length}`} inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'} maxLength={i === 0 ? length : 1}
          value={value[i] ?? ''} onFocus={e => e.currentTarget.select()}
          onChange={e => insert(i, e.target.value)}
          onPaste={e => { e.preventDefault(); insert(i, e.clipboardData.getData('text')); }}
          onKeyDown={onKey(i)} />
      ))}
    </div>
  );
}
```
(`select()` on focus means a typed char replaces the box's digit, so `e.target.value` is either one new char or, on box 0, the full autofilled code. Test on real mobile keyboards — I'm not certain every Android IME fires events the same way.)

## Trade-offs & pitfalls
- `type="number"` breaks leading zeros and shows spinners; use `inputMode="numeric"` + `pattern="\d*"`.
- Holes in the value (allowing box 4 filled with 3 empty) complicate everything; keep contiguous, typing past the end writes at the end.
- Auto-submit on complete: show a pending state, disable re-submit, announce errors; on error, clear and focus first box.
- `maxLength=1` on the first box blocks SMS autofill on some platforms; that's why it gets `length`.
- WebOTP API (`navigator.credentials.get({ otp })`) can read SMS on Android Chrome with consent; progressive enhancement only.

## Likely follow-ups
- **Resend timer?** Separate component; countdown announced politely at sensible intervals (see Q07).
- **Alphanumeric codes?** Swap the filter, `inputMode="text"`, `autocapitalize="characters"`.
- **Why one string not an array?** Paste/backspace become string splices; no sparse array bugs.
- **Testing?** `user.type`, `user.paste('12ab56')`, `user.keyboard('{Backspace}')`; assert values, focus and `onComplete` call count.

## Say it in 60 seconds
I model the code as one contiguous string and render it across six single-character inputs, all routed through one insert function that strips non-digits, splices at the index and moves focus. Typing, paste on any box, and SMS autofill — via `autocomplete="one-time-code"` on the first box, which accepts the full length — all use that path. Backspace clears the current box or moves left and clears; arrows move focus. `onComplete` fires only on the transition to complete. For accessibility there's a labelled group, "Digit 3 of 6" labels and numeric input mode. If design allows, I'd actually prefer a single input styled as boxes, since native paste, autofill and screen reader behavior then come for free.
