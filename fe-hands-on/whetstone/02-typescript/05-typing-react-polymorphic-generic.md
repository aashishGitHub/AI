# Type React components well: polymorphic as props, generic components and forwarding props
**Round:** 02 · TypeScript for Real Codebases · **Level:** Lead / Staff · **Time:** 18 min · **Tags:** react · typescript · polymorphic components
Source: https://whetstone-v1.vercel.app/#typescript

## What they're really testing
Design-system typing judgement: extend native props correctly, make collection components generic, handle refs in React 19, and know when polymorphic `as` is worth its cost versus `asChild`. (Site has React/Angular/Vue tabs; notes are React.)

Test cases given: `<Button as="a" href="/x">` compiles, `<Button as="a" type="submit">` doesn't; `<Select options={users} getLabel={u => u.name} onSelect={u => u.id} />` infers `u: User`.

## Core answer (key points)
- **Extend native elements** with `ComponentProps<'button'>` (or `ComponentPropsWithoutRef`/`WithRef`), `Omit` what you redefine, spread `...rest` onto the root. All `aria-*`, `data-*`, handlers keep working.
- Default `type="button"` on buttons to stop accidental form submits.
- **Generic components**: declare `function Listbox<T>(props: ListboxProps<T>)`; `T` is inferred from `items`, so callbacks get the item type.
- **React 19**: `ref` is a regular prop on function components; `forwardRef` is no longer needed (still works, slated for deprecation per React docs).
- **Polymorphic `as`**: powerful but expensive (slow checking at scale, confusing errors) and easy to misuse semantically (`as="div"` with button behaviour). Many systems prefer **`asChild`/Slot** (Radix): the consumer supplies the element, the component merges props and ref into it.
- Avoid `React.FC`: poor generics story, historically implicit `children`.

## Mental model / flow
```
Polymorphic: <Text as={E}>  ->  props = OwnProps & Omit<ComponentProps<E>, keyof OwnProps>
asChild:     <Trigger asChild><Link/></Trigger>  ->  Slot clones child, merges props/ref/handlers
```

## Code sketch
```tsx
import type { ComponentPropsWithRef, ElementType, ReactNode } from 'react';

type Own = { variant?: 'primary' | 'ghost' };

type ButtonProps =
  | (Own & { as?: 'button' } & ComponentPropsWithRef<'button'>)
  | (Own & { as: 'a'; type?: never } & Omit<ComponentPropsWithRef<'a'>, 'type'>);

export function Button(props: ButtonProps) {
  if (props.as === 'a') {
    const { as: _as, variant = 'ghost', ...rest } = props;
    return <a data-variant={variant} {...rest} />;
  }
  const { as: _as, variant = 'ghost', type = 'button', ...rest } = props;
  return <button type={type} data-variant={variant} {...rest} />;
}
```
Why the explicit `type?: never`: `<a>` has a real `type` attribute (MIME hint) in React's types, so a naive polymorphic type would *accept* `as="a" type="submit"`.

```tsx
type ListboxProps<T> = {
  items: readonly T[];
  getKey: (item: T) => string;
  render: (item: T) => ReactNode;
  onSelect: (item: T) => void;
};

export function Listbox<T>({ items, getKey, render, onSelect }: ListboxProps<T>) {
  return (
    <ul role="listbox">
      {items.map((it) => (
        <li key={getKey(it)} role="option" aria-selected={false} onClick={() => onSelect(it)}>
          {render(it)}
        </li>
      ))}
    </ul>
  );
}

type TextProps<E extends ElementType> = { as?: E; tone?: 'muted' | 'default' }
  & Omit<ComponentPropsWithRef<E>, 'as' | 'tone'>;
export function Text<E extends ElementType = 'span'>({ as, tone = 'default', ...rest }: TextProps<E>) {
  const Tag: ElementType = as ?? 'span';
  return <Tag data-tone={tone} {...rest} />;
}
```
In `.tsx`, an arrow generic needs `<T,>` to disambiguate from JSX; function declarations avoid that.

## Trade-offs & pitfalls
- Polymorphic types multiply checker work for every usage; at design-system scale this shows up in editor latency.
- `as` lets consumers break semantics (`<Button as="div">` loses keyboard/role); `asChild` keeps the element choice explicit but relies on `cloneElement`-style merging (handler composition, ref merging must be correct).
- `ComponentProps<'x'>` includes `ref` under React 19 types; spreading `rest` forwards it, which is what you want on the root.
- Handler typing: let inference work via the prop type (`onChange: ComponentProps<'input'>['onChange']`) rather than hand-writing `React.ChangeEvent<...>` everywhere.

## Likely follow-ups
- **Component that takes `href` or `onClick`?** Discriminated prop union (`{ href: string } | { onClick: () => void; href?: never }`) rendering `<a>` vs `<button>`, keeping semantics correct.
- **Context without `undefined` checks everywhere?** `createContext<V | null>(null)` + a `useX()` hook that throws outside the provider and returns `V`.
- **`children` typing?** `ReactNode` for content, `(state: S) => ReactNode` for render props.
- **Generic component with `memo`?** `memo` loses generics; re-assert the signature: `export const List = memo(ListImpl) as typeof ListImpl`. A contained, conventional cast.

## Say it in 60 seconds
For native-like components I take `ComponentProps` of the element, omit what I redefine, and spread the rest onto the root, so every aria attribute, handler and, in React 19, the ref just works without `forwardRef`. Collection components are generic, so `T` is inferred from `items` and `onSelect` receives a `User` with no annotations. For buttons that can be links I prefer a discriminated prop union over a fully polymorphic `as`, partly because anchors have their own `type` attribute, so a naive polymorphic type would accept `type="submit"` on a link. Fully polymorphic `as` is fine for a Text primitive, but it's slow to type-check at scale and lets consumers break semantics, which is why I often reach for Radix-style `asChild`, where the consumer supplies the element and the component merges props into it.
