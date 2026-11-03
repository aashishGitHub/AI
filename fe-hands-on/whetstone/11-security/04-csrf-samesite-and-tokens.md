# CSRF today: SameSite cookies, tokens, and when you still need both
**Round:** 11 · Frontend Security · **Level:** Senior · **Time:** 10 min · **Tags:** csrf · samesite · cookies
Source: https://whetstone-v1.vercel.app/#security

Scenario: cookie-session API; a pen tester forges a cross-site POST that changes a user's email. "SameSite=Lax is default, so CSRF is solved?"

## What they're really testing
Do you know the precise gaps in SameSite (site ≠ origin, Lax allows top-level GET, legacy/None cookies) and the layered server-side defenses?

## Core answer (key points)
- **CSRF mechanics:** attacker page triggers a request to your origin; the browser auto-attaches your cookies; server trusts the cookie as intent.
- **SameSite:**
  - `Strict`: cookie never sent on cross-site requests, including clicking a link to you (annoying for inbound links).
  - `Lax`: sent on top-level GET navigations, not on cross-site POSTs, iframes, images, fetch. Modern Chromium defaults unset cookies to Lax; I'm not certain all browsers default the same way, so set it explicitly.
  - `None` (+Secure): sent everywhere; needed for genuine cross-site embeds; full CSRF exposure.
- **Why Lax isn't "solved":**
  1. GET with side effects still works (`<a href="/delete?id=1">`, top-level nav).
  2. *Same-site* is registrable domain (eTLD+1): `blog.acme.com` is same-site with `app.acme.com`. A compromised or user-content subdomain can CSRF you.
  3. Legacy browsers, `SameSite=None` cookies, misconfigured frameworks.
  4. Chromium had a temporary "Lax+POST" two-minute exception for newly set cookies without SameSite (verify whether still present).
- **Layered defenses:**
  - Never mutate on GET.
  - Session cookie: `SameSite=Lax` or `Strict`, `__Host-` prefix, `Secure`, `HttpOnly`.
  - Server checks on unsafe methods: `Origin` header must match; reject `Sec-Fetch-Site: cross-site` (Fetch Metadata) unless the endpoint is meant to be cross-site.
  - CSRF token: synchronizer (server-stored, per session) or signed double-submit (HMAC bound to the session id, sent in cookie + header).
  - Require a custom header / JSON content type: cross-origin requests with those trigger a CORS preflight the attacker can't pass.
- **Not CSRF-vulnerable:** APIs authenticated only by an `Authorization` header set by JS. The browser doesn't attach it automatically. They trade CSRF risk for XSS token-theft risk.
- **CSRF vs XSS vs CORS:** CSRF abuses ambient credentials without reading responses; XSS runs script in your origin (game over, bypasses CSRF tokens); CORS controls who may *read* cross-origin responses, it does not stop the request being sent.

## Mental model / flow
```
evil.com form POST ──► app.acme.com/email
  browser: cross-site + SameSite=Lax ──► cookie NOT attached ─► 401 ✔
blog.acme.com (compromised) POST ──► same-site! cookie attached
  server: Sec-Fetch-Site=same-site? Origin != app origin? ─► reject ✔
          missing/invalid X-CSRF-Token ─► reject ✔
```

## Code sketch
```ts
// server middleware (Express-style sketch)
const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);
export function csrfGuard(req: Req, res: Res, next: Next) {
  if (SAFE.has(req.method)) return next();
  const site = req.headers['sec-fetch-site'];
  if (site && site !== 'same-origin' && site !== 'none') return res.status(403).end();
  if (req.headers.origin && req.headers.origin !== APP_ORIGIN) return res.status(403).end();
  const header = req.headers['x-csrf-token'];
  if (!header || !timingSafeEqual(header, hmac(req.sessionId))) return res.status(403).end();
  next();
}
```

## Trade-offs & pitfalls
- Double-submit without signing is weak if an attacker can set cookies (subdomain cookie tossing); bind to the session with HMAC.
- `Sec-Fetch-*` headers are absent in older browsers; treat missing as "fall back to token check", not "allow".
- Login CSRF (forcing victim into attacker's account) is real; protect the login form and OAuth callback (`state`).
- Strict on the main session cookie breaks inbound-link UX; common pattern: Lax session cookie + Strict cookie for sensitive actions.

## Likely follow-ups
- *How do you test?* Host an HTML page on another origin/subdomain posting a form; Burp-style removal of token/Origin; confirm 403.
- *Does CORS protect POSTs?* No; "simple" requests (form-encoded POST) are sent without preflight; CORS only hides the response.
- *GraphQL endpoint?* Same rules; ensure it rejects `GET` mutations and `text/plain` content types.
- *Which wins if there's XSS?* XSS reads the CSRF token from the page; CSRF defenses assume no XSS.

## Say it in 60 seconds
CSRF works because the browser attaches cookies to requests another site triggers. SameSite=Lax blocks cookies on cross-site POSTs and subresources, which stops most of it, but not all. Lax still sends cookies on top-level GETs, so never mutate on GET. Same-site means registrable domain, so a compromised sibling subdomain is trusted. And legacy or `SameSite=None` cookies exist. So I layer it: explicit Lax or Strict on a `__Host-` session cookie, server checks of `Origin` and `Sec-Fetch-Site` on unsafe methods, and a session-bound CSRF token or required custom header that forces a preflight. Header-token APIs aren't classic-CSRF targets, but they trade that for XSS exposure. CORS governs reading responses, not sending requests.
