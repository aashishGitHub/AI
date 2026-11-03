# Review a component API: props explosion, boolean flags, slots and composition
**Round:** 05 · Component API Design · **Level:** Lead / Staff · **Time:** 12 min · **Tags:** component api · code review · composition
Source: https://whetstone-v1.vercel.app/#component-api-design

## What they're really testing
A PR adds a seventh boolean to `<Modal>` (`isCentered`, `noPadding`, `hasFooter`, `wide`...). Can you name the smell, propose a better API, deliver feedback kindly, and plan a non-breaking migration with API tests?

## Core answer (key points)
- **Smell:** API by accretion. N booleans = 2^N combinations, most untested or impossible (`wide` + `fullscreen`?).
- **Find the real variants:** grep call sites, cluster the combinations actually used; usually 2-4 real variants hide behind 7 flags.
- **Replacements:**
  - Booleans encoding a variant → **union**: `size: 'sm' | 'md' | 'lg' | 'fullscreen'`, `placement: 'center' | 'top'`.
  - Content props (`footerText`, `titleIcon`) → **children/slots**: `Modal.Header`, `Modal.Body`, `Modal.Footer`.
  - Props configuring internal structure (`hasFooter`, `noPadding`) → **composition** (omit the footer part; `Modal.Body padding="none"`).
  - Mutually exclusive props → **discriminated unions** (`href` xor `onClick`).
  - Stateful bits → controlled/uncontrolled (`open`/`defaultOpen`/`onOpenChange`).
  - Behavior reuse across visuals → headless parts.
- **Checklist to say out loud:** unions over booleans; content via children; pass-through native props (`...rest`, `className`, `data-*`, `aria-*`, `ref`); intent-named events with consistent signatures; no impossible states; accessible by default (required `aria-label` is a required prop); system consistency over local cleverness; explicit escape hatches (`asChild`, `className`), not "style any internal".
- **Giving feedback:** praise the need, question the shape ("which combos do we actually ship?"), offer the alternative with a call-site example, keep it non-blocking if a migration is planned.
- **Migration:** add new API alongside; old booleans map onto it with a dev-only deprecation warning; codemod (jscodeshift/ts-morph) for call sites; remove in next major.
- **API tests:** type tests (`@ts-expect-error` for impossible combos, `expectTypeOf`), behavior tests (focus trap, Esc, `aria-labelledby`), and visual regression per variant.

## Mental model / flow
```
before:  <Modal isCentered noPadding hasFooter wide footerText="Save" onFooterClick={...} />
after:   <Modal open onOpenChange size="lg" placement="center">
           <Modal.Header><Modal.Title>Edit</Modal.Title></Modal.Header>
           <Modal.Body padding="none">...</Modal.Body>
           <Modal.Footer><Button onClick={save}>Save</Button></Modal.Footer>
         </Modal>
```

## Code sketch
```tsx
type ModalSize = 'sm' | 'md' | 'lg' | 'fullscreen';

type ModalProps = {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  size?: ModalSize;
  placement?: 'center' | 'top';
  children: ReactNode;
} & ({ 'aria-label': string } | { 'aria-labelledby': string }); // must be named

type LinkOrButton =
  | ({ href: string; onClick?: never } & ComponentProps<'a'>)
  | ({ onClick: () => void; href?: never } & ComponentProps<'button'>);

// Type-level API tests
// @ts-expect-error href and onClick together is impossible
const bad: LinkOrButton = { href: '/x', onClick: () => {} };

// Deprecation shim
function LegacyModal({ wide, isCentered, ...rest }: ModalProps & { wide?: boolean; isCentered?: boolean }) {
  if (process.env.NODE_ENV !== 'production' && (wide !== undefined || isCentered !== undefined)) {
    console.warn('[Modal] `wide`/`isCentered` are deprecated. Use size="lg" / placement="center".');
  }
  return <Modal {...rest} size={rest.size ?? (wide ? 'lg' : 'md')} placement={rest.placement ?? (isCentered ? 'center' : 'top')} />;
}
```

## Trade-offs & pitfalls
- Composition is more verbose for the 80% case; offer a convenience wrapper (`<ConfirmDialog title onConfirm />`) on top.
- Slots via compound parts add context coupling (see Q01).
- Over-abstracting: don't add a variant system for a component used in 3 places.
- Escape hatches like `className` on every internal part become a de facto API you can't change; be stingy.
- Migration codemods miss dynamic props (`{...props}`); keep the shim until telemetry shows zero usage.

## Likely follow-ups
- **How do you know which combos are used?** Static analysis of call sites (AST scan) or runtime telemetry of prop usage in dev builds.
- **`asChild` pattern?** Render behavior onto the consumer's element (Radix Slot) instead of a fixed tag; merges props/refs.
- **Who owns API decisions?** Design-system RFC with consumers; API review checklist in PR template.
- **What breaks semver?** Removing props, changing defaults, changing DOM structure consumers style against.

## Say it in 60 seconds
Seven booleans means 128 combinations, most of which nobody has tested, so I'd first find which combinations actually ship. Booleans that are really variants become unions like `size` and `placement`; content props become slots like `Modal.Header`, `Modal.Body` and `Modal.Footer`; structural flags like `hasFooter` disappear because you just don't render the footer; mutually exclusive props become discriminated unions. Native props pass through, open state is controllable, and an accessible name is a required prop. I'd say it kindly with a call-site example, keep the old props working behind a dev deprecation warning with a codemod, and lock the new API with type tests, behavior tests and visual regression per variant.
