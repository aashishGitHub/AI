# XSS in React apps: where React protects you, where it doesn't, and how to sanitize
**Round:** 11 · Frontend Security · **Level:** Senior · **Time:** 15 min · **Tags:** xss · react · sanitization
Source: https://whetstone-v1.vercel.app/#security

Scenario: PM wants rich-text comments with links and images; security asks how React protects you and where it doesn't.

## What they're really testing
Can you enumerate the injection sinks React does *not* cover, and design a rich-text pipeline that never stores or renders arbitrary HTML?

## Core answer (key points)
- **What React gives you:** JSX children and attribute values are set as text / properties, so `<p>{body}</p>` can't create elements. That kills most reflected/stored XSS in normal rendering.
- **Where it doesn't help (the sinks):**
  - `dangerouslySetInnerHTML` with user HTML.
  - URL attributes: `href`/`src`/`formAction` with `javascript:` (React logs a warning; I believe newer versions block it, but verify for your version, and don't rely on it).
  - Direct DOM: `ref.current.innerHTML`, `insertAdjacentHTML`, `document.write`, jQuery-era code.
  - SSR state inlined in `<script>`: a string containing `</script>` breaks out of the tag.
  - `eval`, `new Function`, `setTimeout(string)`.
  - Third-party widgets and tag managers (run with full origin privileges).
  - `postMessage` handlers that render `event.data` without checking `event.origin`.
  - Inline SVG uploads (SVG can carry script); DOM-based XSS from `location.hash`/query in non-React code.
- **Design for rich text:** store a structured document (ProseMirror/Lexical/Slate JSON, or Markdown) and render through a fixed set of node components. If HTML is unavoidable, sanitize with DOMPurify using a tight tag/attr allowlist, at **output** time (sanitizer rules improve; re-sanitizing on render covers old stored data). Optionally also sanitize on input to reject junk early.
- **URLs:** parse with `new URL()` and allowlist protocols (`https:`, `http:`, `mailto:`). Add `rel="noopener noreferrer ugc"` to user links. Images: proxy or restrict to your CDN.
- **SSR state:** emit as `<script type="application/json">` and `JSON.parse(textContent)`, or escape `<`, U+2028, U+2029.
- **Defense in depth:** strict CSP (nonces + `strict-dynamic`), Trusted Types to make string-to-sink assignment throw. Test with a payload corpus in unit/E2E tests.

## Mental model / flow
```
user input ─► store as structured doc / markdown (never trusted HTML)
                       │
render ─► known node types ─► React text/props (escaped) ✔
     └─► (if HTML) DOMPurify allowlist ─► Trusted Types policy ─► innerHTML
                                             ▲ CSP blocks anything that slipped past
```

## Code sketch
```ts
import DOMPurify from 'dompurify';

const ALLOWED_PROTOCOLS = ['https:', 'http:', 'mailto:'];
export const safeHref = (raw: string): string | undefined => {
  try { const u = new URL(raw, location.origin); return ALLOWED_PROTOCOLS.includes(u.protocol) ? u.href : undefined; }
  catch { return undefined; }
};

export const cleanCommentHtml = (dirty: string) =>
  DOMPurify.sanitize(dirty, {
    ALLOWED_TAGS: ['p', 'strong', 'em', 'a', 'ul', 'ol', 'li', 'code', 'blockquote'],
    ALLOWED_ATTR: ['href'],
  });

// SSR state without a script-breakout risk
const stateTag = `<script id="__state" type="application/json">${JSON.stringify(state).replace(/</g, '\\u003c')}</script>`;
// client: JSON.parse(document.getElementById('__state')!.textContent!)
```

## Trade-offs & pitfalls
- Sanitize-on-input only: when the sanitizer later gains a fix, old stored payloads stay dangerous.
- DOMPurify must run in a real DOM (browser or jsdom on server); string regex "sanitizers" are broken by design.
- Allowing `style` or `class` attrs opens CSS injection / UI redress; keep the allowlist minimal.
- Markdown renderers often allow raw HTML by default; turn it off.
- Sanitizing then mutating (e.g. string concatenation after sanitize) can reintroduce XSS (mutation XSS). Sanitize last, right before the sink.

## Likely follow-ups
- *Stored vs reflected vs DOM XSS?* Stored: persisted then served; reflected: echoed from request; DOM: client JS moves a source (URL, postMessage) into a sink.
- *Does HttpOnly cookie make XSS fine?* No; script can still act as the user in-page, it just can't exfiltrate the cookie.
- *How do you test?* OWASP payload list through render paths; unit tests on `safeHref`; CSP reports in prod as a canary.
- *Image XSS?* `<img onerror>` is blocked by sanitizer attr allowlist; SVG files served from a separate sandbox domain or via `<img>`.

## Say it in 60 seconds
React escapes text and attribute values, so ordinary rendering is safe. It doesn't help with `dangerouslySetInnerHTML`, `javascript:` URLs in `href` or `src`, direct `innerHTML`, SSR state inlined into a script tag, eval-style APIs, third-party widgets or unchecked `postMessage`. For rich comments I wouldn't store HTML at all: store a structured document or Markdown with raw HTML off, and render through known node components. If HTML is unavoidable, I run DOMPurify with a tight allowlist at render time, right before the sink. Links get protocol-allowlisted through `new URL`, and SSR state goes in a JSON script tag. Then strict CSP and Trusted Types catch whatever slips through, and payload tests guard regressions.
