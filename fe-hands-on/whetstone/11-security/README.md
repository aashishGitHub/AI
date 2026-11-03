# 11 · Frontend Security
> Where React stops protecting you, strict CSP + Trusted Types, token storage and BFF, CSRF beyond SameSite, OAuth code+PKCE, and npm/third-party supply chain · 6 questions · ~1 h 19 min
Source: https://whetstone-v1.vercel.app/#security

| # | Question | Level | Time | Tags | Notes |
|---|----------|-------|------|------|-------|
| 01 | XSS in React apps: where React protects you, where it doesn't, and how to sanitize | Senior | 15 min | xss · react · sanitization | [notes](01-xss-in-react-apps.md) |
| 02 | Content Security Policy with nonces and Trusted Types: rolling it out without breaking production | Lead / Staff | 15 min | csp · content security policy · trusted types | [notes](02-strict-csp-and-trusted-types.md) |
| 03 | Where should a single-page app keep auth tokens? Cookies vs memory vs storage, and the BFF pattern | Lead / Staff | 15 min | authentication · tokens · cookies | [notes](03-spa-token-storage-and-bff.md) |
| 04 | CSRF today: SameSite cookies, tokens, and when you still need both | Senior | 10 min | csrf · samesite · cookies | [notes](04-csrf-samesite-and-tokens.md) |
| 05 | OAuth 2.1 with PKCE for browser apps, step by step | Lead / Staff | 12 min | oauth · pkce · oidc | [notes](05-oauth-pkce-for-browser-apps.md) |
| 06 | Frontend supply-chain security: dependencies, lockfiles, SRI and third-party scripts | Lead / Staff | 12 min | supply chain · dependencies · npm | [notes](06-frontend-supply-chain-security.md) |

## How these connect
- One threat runs through all six: attacker-controlled script executing in your origin. 01 is how it gets in, 02 is how you stop it running, 06 is the "it came from a dependency" variant.
- 03 → 04 → 05 form the auth chain: where credentials live (03), the cost of choosing cookies (04), and how you obtain the tokens in the first place (05). Study as one block.
- Key cross-link: HttpOnly cookies (03) stop token *exfiltration*, not XSS; so 01/02 remain the primary defense even with a BFF.
- Suggested order: 01 → 02 → 06 (script-execution block), then 03 → 05 → 04 (auth block).
