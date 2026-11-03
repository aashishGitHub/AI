# CORS end to end: simple vs preflighted requests, credentials and common misconfigurations
**Round:** 07 · Browser & Web Platform · **Level:** Senior · **Time:** 12 min · **Tags:** cors · preflight · credentials
Source: https://whetstone-v1.vercel.app/#browser-platform

Scenario: SPA on `app.example.com` calls `api.example.com`. A JSON `PUT` is blocked, a plain `GET` works. A backend dev set `Access-Control-Allow-Origin: *` and now cookies broke.

## What they're really testing
Precise knowledge of the preflight trigger rules and the credentials rules, plus security judgment: what CORS is and isn't.

## Core answer (key points)
- **What CORS is:** the browser enforces same-origin policy on *reading* responses. CORS is the server opting in, via response headers, to let a specific other origin read them. It's a browser-side relaxation, not server protection.
- **Simple request** (no preflight): method `GET`/`HEAD`/`POST`, only CORS-safelisted headers, and `Content-Type` limited to `text/plain`, `multipart/form-data`, `application/x-www-form-urlencoded`. The request is sent; the browser just hides the response unless `Access-Control-Allow-Origin` matches.
- **Preflighted:** anything else, e.g. `PUT`/`DELETE`/`PATCH`, `Content-Type: application/json`, `Authorization`, any custom header. Browser first sends `OPTIONS` with `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`. Server must answer (2xx) with matching `Allow-Origin`, `Allow-Methods`, `Allow-Headers`. That's why the JSON PUT fails and the GET works.
- **Credentials** (cookies, HTTP auth; `fetch(..., { credentials: 'include' })`):
  - Server must return the exact origin, not `*`, plus `Access-Control-Allow-Credentials: true`.
  - With credentials, `*` is also not allowed for `Allow-Headers`/`Allow-Methods`/`Expose-Headers` (treated literally). That's why the `*` "fix" broke cookies.
  - Cookies also need the right `SameSite`/`Secure` attributes; `app.` and `api.` on the same registrable domain are same-site, so `SameSite=Lax` cookies can flow, but cross-site setups need `SameSite=None; Secure`.
- **Dynamic origin → `Vary: Origin`**, or a CDN caches the response for origin A and serves it to origin B.
- **What CORS does not do:** it doesn't authenticate, doesn't stop curl/server-to-server, and doesn't prevent CSRF (requests still go out; attacker just can't read the reply).

## Mental model / flow
```
Browser (app.acme.com)                         API (api.acme.com)
OPTIONS /orders
  Origin: https://app.acme.com
  Access-Control-Request-Method: PUT
  Access-Control-Request-Headers: content-type, authorization   ─►
                                               ◄─ 204
                                                  Access-Control-Allow-Origin: https://app.acme.com
                                                  Access-Control-Allow-Methods: PUT, DELETE
                                                  Access-Control-Allow-Headers: content-type, authorization
                                                  Access-Control-Allow-Credentials: true
                                                  Access-Control-Max-Age: 600
                                                  Vary: Origin
PUT /orders (actual)                          ─►
                                               ◄─ 200 + Allow-Origin + Allow-Credentials
```

## Code sketch
```ts
// Express-style allowlist middleware (illustrative).
const ALLOWED = new Set(['https://app.acme.com', 'https://admin.acme.com']);

app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && ALLOWED.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
  }
  res.setHeader('Vary', 'Origin');
  if (req.method === 'OPTIONS') {
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE');
    res.setHeader('Access-Control-Allow-Headers', 'content-type,authorization');
    res.setHeader('Access-Control-Max-Age', '600');
    return res.sendStatus(204); // before auth middleware
  }
  next();
});
```

## Trade-offs & pitfalls
- **Reflecting any `Origin` with credentials** = any site can read your users' data. Always allowlist.
- **Allowing `Origin: null`**: sandboxed iframes and `file://` send `null`; attackers can produce it too.
- **Missing `Vary: Origin`** with a dynamic allow-origin poisons shared caches.
- **Auth middleware before CORS**: preflight carries no credentials, gets 401, browser reports a CORS error.
- **Regex allowlists** like `/acme\.com$/` match `evilacme.com`. Anchor and compare exact origins.
- **Preflight cost:** an extra round trip per (URL, method, headers) until `Max-Age` expires; browsers cap max-age (Chromium ~2h, I'm not certain of current Firefox cap). Biggest win: same-origin reverse proxy (`app.acme.com/api → backend`) removes CORS entirely.

## Likely follow-ups
- **Does CORS prevent CSRF?** No. Form POSTs are "simple" and go out with cookies. Use SameSite cookies plus CSRF tokens or custom-header checks.
- **Why only "TypeError: Failed to fetch"?** The browser deliberately hides CORS failure details from JS; read the console and Network panel.
- **How does JS read a custom response header?** Server must list it in `Access-Control-Expose-Headers`.
- **`mode: 'no-cors'`?** Sends the request but gives an opaque response you can't read; rarely what you want.
- **Private Network Access?** Chromium adds a preflight for public→private network requests; mention as newer and verify current status.

## Say it in 60 seconds
CORS is the browser relaxing same-origin policy when the server opts in with headers. Simple requests, meaning GET, HEAD or POST with safelisted headers and form-style content types, are sent directly and the browser just withholds the response if the origin isn't allowed. A JSON PUT or anything with Authorization triggers an OPTIONS preflight first, and the server must answer with matching allowed origin, methods and headers; that's why GET worked and PUT didn't. For cookies you need an exact origin, not star, plus Allow-Credentials true, and Vary: Origin so caches don't mix origins. The dangerous misconfigurations are reflecting any origin with credentials, allowing null, and auth middleware rejecting the preflight. And CORS isn't auth or CSRF protection; the cleanest fix is often a same-origin proxy.
