# Accessible forms: labels, descriptions, error summaries and validation timing
**Round:** 10 · Accessibility · **Level:** Senior · **Time:** 12 min · **Tags:** forms · labels · validation
Source: https://whetstone-v1.vercel.app/#accessibility

Scenario: checkout form uses placeholders as labels, shows errors only in red under the field, has no error summary, and validates on every keystroke.

## What they're really testing
Can you wire label/hint/error to the field programmatically, pick humane validation timing, and handle focus after a failed submit?

## Core answer (key points)
- **Labels:** visible `<label for>` on every field. Placeholder can be an example, never the label.
- **Hints and errors:** give each an id and reference both from `aria-describedby="x-hint x-error"`. Set `aria-invalid="true"` only when invalid.
- **Groups:** radios/checkbox sets and composite inputs (date parts, address) in `<fieldset>` + `<legend>`.
- **Not colour alone (WCAG 1.4.1):** add an icon and text ("Error:" prefix) next to red.
- **Timing:** validate on blur or on submit, not from the first keystroke. A common refinement: once a field has been flagged, re-validate it on input so the error clears as soon as it's fixed.
- **On submit with errors:** either focus the first invalid field, or render an error summary at the top (heading + list of links to each field), focus it, and keep the inline errors. GOV.UK pattern is the well-known reference.
- **Error copy:** say what's wrong and how to fix it, use the label's words, show format examples in the hint up front.
- **Input purpose:** `type="email|tel|number"`, `inputmode`, and `autocomplete` tokens (`email`, `given-name`, `cc-number`, `one-time-code`, `new-password`). WCAG 1.3.5 Identify Input Purpose.
- **Required:** mark visually and with `required`/`aria-required`; explain the convention once.
- **Don't:** block paste in passwords, auto-advance focus between fields (OTP is a careful exception), clear user input on error.

## Mental model / flow
```
<label for=email>──┐
<p id=email-hint>──┼──► <input id=email aria-describedby="email-hint email-error" aria-invalid>
<p id=email-error>─┘          SR reads: name (label) + description (hint, error) + "invalid"

submit ─► validate all ─► errors? ─ no ─► proceed
                              └ yes ─► render summary (role=alert/tabindex -1) ─► focus it
                                         links #field ─► jump to field
```

## Code sketch
```tsx
function Field({ id, label, hint, error, ...input }: FieldProps) {
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined;
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      {hint && <p id={`${id}-hint`}>{hint}</p>}
      <input id={id} aria-describedby={describedBy} aria-invalid={error ? true : undefined} {...input} />
      {error && <p id={`${id}-error`}><span aria-hidden="true">⚠ </span>Error: {error}</p>}
    </div>
  );
}

function Summary({ errors }: { errors: { id: string; msg: string }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (errors.length) ref.current?.focus(); }, [errors]);
  if (!errors.length) return null;
  return (
    <div ref={ref} tabIndex={-1} aria-labelledby="sum-h">
      <h2 id="sum-h">There is a problem</h2>
      <ul>{errors.map(e => <li key={e.id}><a href={`#${e.id}`}>{e.msg}</a></li>)}</ul>
    </div>
  );
}
```

## Trade-offs & pitfalls
- Focus summary vs focus first field: summary is better for long forms (user sees all problems); first-field is fine for 2-3 fields. Don't do both.
- Adding `role="alert"` to a summary that you also focus may double-announce on some SRs; pick one mechanism and test.
- `novalidate` on the form if you render custom errors, otherwise native bubbles and yours both appear.
- Error summary effect keyed on the `errors` array identity: re-renders with a new array re-focus it. Key on submit attempts instead.
- Live validation per keystroke on an empty field shouts errors before the user has typed.

## Likely follow-ups
- *Native constraint validation or custom?* Native messages are inconsistent and hard to style or localise; most design systems use `novalidate` + custom messages, but still use `required`/`type` for semantics.
- *Async validation (username taken)?* Debounce, show inline, announce politely.
- *Multi-step checkout?* Each step gets a heading focus on transition, step indicator with `aria-current="step"`.
- *How to test?* Keyboard-only submit with errors, SR reads label+hint+error, zoom 200% / 400% reflow, axe for missing labels.

## Say it in 60 seconds
Every field gets a visible `<label>`; placeholders are only examples. Hints and errors have ids referenced by `aria-describedby`, invalid fields get `aria-invalid`, and related controls sit in a `fieldset` with a `legend`. Errors use text and an icon, not only red. I validate on blur or submit, then re-check live once a field is flagged so it clears as you fix it. On a failed submit I either focus the first invalid field or, for long forms, show an error summary with links to each field and focus that. Messages say how to fix the problem. And I add correct input types and `autocomplete` tokens, never block paste, and test with keyboard, a screen reader and zoom.
