# Production forms with react-hook-form and zod: validation, async checks, server errors and field arrays
**Round:** 05 · Component API Design · **Level:** Senior · **Time:** 18 min · **Tags:** forms · react-hook-form · zod
Source: https://whetstone-v1.vercel.app/#component-api-design

## What they're really testing
A signup form with email, password, a repeatable "team members" list, an async "username available" check, and server-side errors that land on the correct fields. One zod schema shared client/server; validation that doesn't shout while typing; accessible errors.

Tests from the prompt: empty submit shows errors and focuses first invalid; taken username marks only that field and blocks submit; a 422 `{ email: 'already used' }` lands on email; adding/removing members keeps values and errors aligned.

## Core answer (key points)
- **Why RHF:** inputs stay uncontrolled, values live in refs → typing doesn't re-render the whole form. `register` wires name/ref/onChange/onBlur.
- **One schema:** `zod` schema → `z.infer` for types, `zodResolver` for client validation, same schema in the API handler. Cross-field rules (`password === confirm`, unique emails) via `refine`/`superRefine` with a `path`.
- **Three error sources, handled separately:**
  1. **Schema** — sync, from resolver.
  2. **Async checks** — username availability on blur, debounced, cancellable (AbortController), "Checking…" only after ~300 ms.
  3. **Server** — map 409/422 field errors back with `setError(name, { message }, { shouldFocus })`; generic failures into `root.server`.
- **Timing:** `mode: 'onTouched'` (validate after first blur, then on change). All errors on submit; focus the first invalid (RHF default `shouldFocusError`).
- **Field arrays:** `useFieldArray`; key rows by `field.id`, never index, so values and errors stay aligned on remove.
- **A11y:** real `<label>`s, `aria-invalid`, `aria-describedby` → error text id, `fieldset/legend` for the member group, `role="alert"` for the form-level error.
- **UX rules:** keep submit enabled (validate on click so users learn why), never clear input on failure, unsaved-changes guard only if `isDirty`.
- **Server must re-check** username anyway: the check and the submit can race.

## Mental model / flow
```
type → (onTouched) resolver(zod) → errors.field
blur username → debounce 300ms → abort prev → GET /available?u= → setError / clearErrors
submit → resolver → invalid? focus first, stop
       → POST → 201 ok
              → 422 {fieldErrors} → setError per field, focus first
              → 5xx → setError('root.server')
```

## Code sketch
```tsx
const Signup = z.object({
  email: z.string().email('Enter a valid email'),
  username: z.string().min(3, 'At least 3 characters').regex(/^[a-z0-9_]+$/i, 'Letters, numbers, _'),
  password: z.string().min(12, 'At least 12 characters'),
  members: z.array(z.object({ email: z.string().email('Invalid email') }))
    .superRefine((list, ctx) => {
      const seen = new Set<string>();
      list.forEach((m, i) => {
        const k = m.email.toLowerCase();
        if (seen.has(k)) ctx.addIssue({ code: 'custom', path: [i, 'email'], message: 'Duplicate' });
        seen.add(k);
      });
    }),
});
type SignupValues = z.infer<typeof Signup>;

function useUsernameCheck(setError: UseFormSetError<SignupValues>, clearErrors: UseFormClearErrors<SignupValues>) {
  const ctrl = useRef<AbortController>();
  return async (username: string) => {
    ctrl.current?.abort();
    ctrl.current = new AbortController();
    try {
      const r = await fetch(`/api/username-available/${encodeURIComponent(username)}`, { signal: ctrl.current.signal });
      const { available } = await r.json();
      available ? clearErrors('username') : setError('username', { type: 'taken', message: 'Username is taken' });
      return available as boolean;
    } catch (e) { if ((e as Error).name !== 'AbortError') throw e; return true; }
  };
}

export function SignupForm() {
  const { register, control, handleSubmit, setError, clearErrors, formState: { errors, isSubmitting } } =
    useForm<SignupValues>({ resolver: zodResolver(Signup), mode: 'onTouched',
      defaultValues: { email: '', username: '', password: '', members: [{ email: '' }] } });
  const { fields, append, remove } = useFieldArray({ control, name: 'members' });
  const checkUsername = useUsernameCheck(setError, clearErrors);

  const onSubmit = handleSubmit(async values => {
    if (!(await checkUsername(values.username))) return setError('username', { message: 'Username is taken' }, { shouldFocus: true });
    const res = await fetch('/api/signup', { method: 'POST', body: JSON.stringify(values) });
    if (res.status === 422) {
      const { fieldErrors } = (await res.json()) as { fieldErrors: Partial<Record<keyof SignupValues, string>> };
      Object.entries(fieldErrors).forEach(([k, msg], i) =>
        setError(k as keyof SignupValues, { type: 'server', message: msg }, { shouldFocus: i === 0 }));
      return;
    }
    if (!res.ok) setError('root.server', { message: 'Could not create your account. Try again.' });
  });

  const field = (name: 'email' | 'username' | 'password', label: string, extra = {}) => (
    <div>
      <label htmlFor={name}>{label}</label>
      <input id={name} {...register(name, extra)} aria-invalid={!!errors[name] || undefined}
             aria-describedby={errors[name] ? `${name}-err` : undefined} />
      {errors[name] && <p id={`${name}-err`}>{errors[name]?.message}</p>}
    </div>
  );

  return (
    <form onSubmit={onSubmit} noValidate>
      {field('email', 'Email')}
      {field('username', 'Username', { onBlur: (e: FocusEvent<HTMLInputElement>) => checkUsername(e.target.value) })}
      {field('password', 'Password')}
      <fieldset>
        <legend>Team members</legend>
        {fields.map((f, i) => (
          <div key={f.id}>
            <label htmlFor={`m-${f.id}`}>Member {i + 1} email</label>
            <input id={`m-${f.id}`} {...register(`members.${i}.email`)} />
            <button type="button" onClick={() => remove(i)} aria-label={`Remove member ${i + 1}`}>Remove</button>
            {errors.members?.[i]?.email && <p>{errors.members[i]?.email?.message}</p>}
          </div>
        ))}
        <button type="button" onClick={() => append({ email: '' })}>Add member</button>
      </fieldset>
      {errors.root?.server && <p role="alert">{errors.root.server.message}</p>}
      <button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Creating…' : 'Create account'}</button>
    </form>
  );
}
```
(Sketch: verify the exact `register(..., { onBlur })` option merging and `root.*` error typing against current RHF docs.)

## Trade-offs & pitfalls
- Async validators inside the zod schema run on every validation pass → network storm. Keep them out or debounce.
- Resolver errors can overwrite a manual `setError` on the next validation; use a distinct `type` and re-apply or check in submit.
- Index keys in field arrays misalign errors after remove.
- Disabled submit buttons hide the reason; prefer enabled + errors.
- Password fields: `autocomplete="new-password"`, don't validate strength aggressively before blur.

## Likely follow-ups
- **Why `noValidate`?** Native bubbles would duplicate/conflict with your messages; keep native `type`/`required` for semantics.
- **Server sharing the schema?** Same package; parse the body with `Signup.safeParse`, return `error.flatten().fieldErrors` as 422.
- **Test strategy?** Testing Library by label/role; MSW to mock 200/409/422/500; assert focus moves to first invalid.
- **When skip RHF?** Tiny forms: React 19 `useActionState` + native validation.

## Say it in 60 seconds
I'd use react-hook-form because fields stay uncontrolled and typing doesn't re-render the form, and a single zod schema gives types, client validation via `zodResolver`, and the same validation on the server. I treat three error sources separately: schema errors, an async username check on blur that's debounced and cancellable, and server 422s that I map back to fields with `setError` and focus the first one. Validation runs on touch then on change so it doesn't nag while typing, everything shows on submit, and the first invalid field gets focus. Team members use `useFieldArray` keyed by its stable id. Accessibility is labels, `aria-invalid`, `aria-describedby` and a fieldset, and I test with Testing Library plus MSW for the server cases.
