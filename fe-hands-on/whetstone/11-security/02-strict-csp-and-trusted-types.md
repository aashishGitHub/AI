# Content Security Policy with nonces and Trusted Types: rolling it out without breaking production
**Round:** 11 · Frontend Security · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** csp · content security policy · trusted types
Source: https://whetstone-v1.vercel.app/#security

Scenario: security wants strict CSP; app has inline scripts, third-party tags, many independently shipping teams.

## What they're really testing
Do you know why nonce + `strict-dynamic` beats host allowlists, how Trusted Types locks DOM sinks, and can you run a staged, report-driven rollout across teams?

## Core answer (key points)
- **CSP = browser-enforced execution allowlist.** It's a mitigation layer: if XSS injects markup, the injected script won't run.
- **Host allowlists are weak:** allowlisted CDNs often host JSONP endpoints or old libraries that can be abused to bypass the policy. Research from Google (web.dev "strict CSP") is the usual reference.
- **Strict CSP:** `script-src 'nonce-<random>' 'strict-dynamic'`. Only `<script nonce=...>` you emitted run; `strict-dynamic` lets those scripts load further scripts (so bundlers and loaders work). Inline event handlers (`onclick=""`) and injected tags are blocked. Add `object-src 'none'`, `base-uri 'none'`. Fallbacks like `https:` and `'unsafe-inline'` are ignored by browsers that understand nonces.
- **Nonce rules:** cryptographically random, unique per response. That means HTML with nonces can't be cached as-is on a CDN: generate at the edge/middleware, or use **hashes** for static HTML.
- **eval:** strict CSP blocks it unless `'unsafe-eval'`; find the offenders (some template engines, old libs).
- **Trusted Types:** `require-trusted-types-for 'script'` makes sinks (`innerHTML`, `script.src`, `eval`) throw on plain strings. Code must pass a `TrustedHTML` from a named policy (e.g. one wrapping DOMPurify). `trusted-types app-html dompurify` restricts which policy names may be created, giving you a small, auditable set. Support: Chromium-based browsers; I'm not certain of current Firefox/Safari status, verify.
- **Rollout plan:**
  1. Inventory every script source: bundles, inline snippets, analytics, tag manager, A/B, chat widgets.
  2. Ship `Content-Security-Policy-Report-Only` with `report-to`; collect and sample reports (they're noisy: extensions inject too).
  3. Fix: remove inline handlers, nonce or externalise inline scripts, pass nonces into the framework (Next.js middleware, CSS-in-JS nonce options).
  4. Negotiate third parties; restrict what the tag manager may inject.
  5. Enforce on one route or % of traffic, watch errors + reports, expand.
  6. Keep the *next* tightening (Trusted Types) in Report-Only while enforcing the current one.
- **Prevent erosion:** policy defined in code with owners; changes reviewed by security; CI test that asserts the header; dashboards on violation reports.
- Related headers: HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, `frame-ancestors` (clickjacking), COOP.

## Mental model / flow
```
request ─► edge/middleware: nonce = random() ─► render HTML with <script nonce>
                                         └─► header: CSP script-src 'nonce-X' 'strict-dynamic'
browser: script tag? nonce match? ─ yes ─► run (+ anything it loads)
                                    └ no ─► block + POST report ─► report collector ─► triage
DOM sink assignment ─► TrustedHTML from policy? ─ no ─► TypeError (enforced) / report (report-only)
```

## Code sketch
```ts
// edge middleware (framework-agnostic sketch)
export function withCsp(html: string) {
  const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
  const csp = [
    `script-src 'nonce-${nonce}' 'strict-dynamic' https: 'unsafe-inline'`,
    `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'self'`,
    `require-trusted-types-for 'script'`, `trusted-types app-html`,
    `report-to csp`,
  ].join('; ');
  return { html: html.replaceAll('%NONCE%', nonce), headers: { 'Content-Security-Policy-Report-Only': csp } };
}

// client: the only sanctioned path to innerHTML
const appHtml = window.trustedTypes?.createPolicy('app-html', { createHTML: s => DOMPurify.sanitize(s) });
export const setHtml = (el: Element, s: string) => {
  el.innerHTML = (appHtml ? appHtml.createHTML(s) : DOMPurify.sanitize(s)) as string;
};
```

## Trade-offs & pitfalls
- Tag managers fundamentally inject arbitrary script; `strict-dynamic` trusts what they load. CSP can't fully contain a tag manager; governance must.
- Nonce reuse across responses (cached HTML) silently destroys the protection.
- Report endpoints get flooded by browser extensions; filter by `source-file`/`blocked-uri`.
- CSS-in-JS injecting `<style>` needs `style-src` nonces too, or `'unsafe-inline'` for styles (lower risk than scripts, but not zero).
- Separate CSP per micro-frontend is hard: one document, one effective policy (multiple policies intersect, they don't union).

## Likely follow-ups
- *Nonce vs hash?* Nonce for dynamic HTML; hash for static/prebuilt pages served from CDN.
- *What does `strict-dynamic` do exactly?* Propagates trust to scripts created by already-trusted scripts and ignores host allowlists.
- *Meta-tag CSP?* Works for most directives but not `frame-ancestors` or reporting; prefer the header.
- *Trusted Types default policy?* A `default` policy catches untyped assignments; useful for migration, risky as a permanent catch-all.

## Say it in 60 seconds
CSP is a browser-enforced allowlist for script execution, so even if XSS lands, injected script doesn't run. I'd use a strict policy, not host allowlists, which are bypassable: a per-response random nonce plus `strict-dynamic`, with `object-src` and `base-uri` set to none. Nonces mean generating HTML at the edge, or using hashes for static pages. On top, Trusted Types makes `innerHTML` and friends throw on plain strings, so every sink goes through a few named, reviewed policies. Rollout: inventory scripts, ship Report-Only, triage reports, remove inline handlers and wire nonces into the framework, push back on third-party tags, then enforce per route or traffic slice. Keep the next step in Report-Only, and guard the policy with code ownership and a CI check.
