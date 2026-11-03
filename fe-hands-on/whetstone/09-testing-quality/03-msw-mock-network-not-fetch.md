# Mock the network, not the fetch function: MSW across unit tests, Storybook and development
**Round:** 09 · Testing & Quality · **Level:** Senior · **Time:** 12 min · **Tags:** msw · mocking · network
Source: https://whetstone-v1.vercel.app/#testing-quality

Scenario: tests mock `fetch` with `jest.fn()` and pass even when the URL, method or payload is wrong. Introduce MSW with one setup shared by tests, Storybook and local dev.

## What they're really testing
Understanding where to put the mock boundary so real client code runs, how MSW works in Node vs browser, testing edge states and request payloads, and keeping mocks honest.

## Core answer (key points)
- **Problem with `fetch = jest.fn()` / `jest.mock('../api')`:** skips your real client (URL building, headers, serialization, error mapping, retries, React Query behavior) and couples tests to file structure. A wrong URL or method still "passes".
- **MSW (Mock Service Worker)** intercepts at the network layer:
  - **Browser:** a real Service Worker intercepts `fetch`/XHR; used for Storybook and local dev.
  - **Node:** `setupServer` from `msw/node` patches Node's request modules / global fetch via interceptors; used in Vitest/Jest.
  - App code is unchanged: real `fetch`, real client.
- **One handler set, three consumers:** `handlers.ts` imported by `setupServer` (tests), `setupWorker` (dev), and the Storybook MSW addon/loader (stories per state).
- **Per-test overrides** with `server.use(...)` for 500, 422 validation errors, empty lists, slow responses (`delay()`), network errors (`HttpResponse.error()`); `resetHandlers()` after each test.
- **`onUnhandledRequest: 'error'`** makes any request without a handler fail the test, catching wrong URLs/methods immediately.
- **Assert what was sent** by reading `request` in the handler (body, headers, search params) and asserting on captured values, or by having the handler return 422 when the payload is wrong so the UI behavior shows it.
- **Keep mocks honest:** generate handlers/fixtures from OpenAPI (e.g. Orval, msw-auto-mock; verify current tool names), or validate fixtures against the same zod schemas the app uses; add contract tests against the real API.

## Mental model / flow
```
component ─► api client ─► fetch ─► [MSW interceptor] ─► handler(request) ─► Response
                (real)      (real)    Node: setupServer
                                      Browser: Service Worker
handlers.ts ──► tests (setupServer) ──► Storybook (addon) ──► dev (setupWorker)
```

## Code sketch
```ts
// mocks/handlers.ts
import { http, HttpResponse, delay } from 'msw';
import { InvoiceSchema } from '../src/api/schemas';

export const handlers = [
  http.get('/api/invoices', () => HttpResponse.json([InvoiceSchema.parse({ id: 'i1', total: 120 })])),
  http.post('/api/invoices', async ({ request }) => {
    const body = (await request.json()) as { total?: number };
    if (typeof body.total !== 'number') {
      return HttpResponse.json({ fieldErrors: { total: 'Required' } }, { status: 422 });
    }
    await delay(100);
    return HttpResponse.json({ id: 'i2', total: body.total }, { status: 201 });
  }),
];

// test/setup.ts
import { setupServer } from 'msw/node';
export const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```
```ts
test('sends the total as a number', async () => {
  let sent: unknown;
  server.use(http.post('/api/invoices', async ({ request }) => {
    sent = await request.json();
    return HttpResponse.json({ id: 'i3', total: 50 }, { status: 201 });
  }));
  const user = userEvent.setup();
  render(<NewInvoice />, { wrapper: AppProviders });
  await user.type(screen.getByRole('spinbutton', { name: /total/i }), '50');
  await user.click(screen.getByRole('button', { name: /create/i }));
  await screen.findByRole('status');
  expect(sent).toEqual({ total: 50 });
});

test('shows retry on server error', async () => {
  server.use(http.get('/api/invoices', () => new HttpResponse(null, { status: 500 })));
  render(<Invoices />, { wrapper: AppProviders });
  expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument();
});
```

## Trade-offs & pitfalls
- MSW mocks can drift from the real API; without schema generation/validation or contract tests you've just moved the lie.
- Handlers with too much logic become a second backend; keep them simple, override per test.
- In jsdom, relative URLs need a base (`location` set by the environment); absolute URLs avoid surprises.
- React Query retries by default will make error tests slow; use a fresh `QueryClient` with `retry: false` per test.
- Service Worker in dev needs the generated worker script in `public/` and HTTPS/localhost.
- MSW 2.x API (`http`, `HttpResponse`) differs from 1.x (`rest`, `res(ctx...)`); know which one the codebase uses.

## Likely follow-ups
- **MSW vs `cy.intercept`/`page.route`?** Those work only inside that E2E tool; MSW is shared across unit, Storybook and dev. In E2E against a real backend, you often don't mock at all except third parties.
- **GraphQL?** MSW has `graphql.query/mutation` handlers keyed by operation name.
- **How do you test loading states?** A handler with `delay('infinite')` or a long delay, then assert the skeleton; do it only if loading UI is a requirement.
- **What about WebSockets/SSE?** Newer MSW versions add WebSocket support; verify for your version.
- **How do you stop untested endpoints slipping through?** `onUnhandledRequest: 'error'` in tests, `'warn'` in dev.

## Say it in 60 seconds
Mocking fetch or the API module skips the code we actually ship, so tests pass with the wrong URL, method or body. MSW mocks at the network layer instead: a real service worker in the browser and request interception in Node, so our real client, headers, serialization and error handling all run. I write one set of handlers and reuse it in Vitest, Storybook and local development, override them per test for 500s, validation errors, empty lists and slow responses, and set unhandled requests to error so a wrong endpoint fails loudly. To assert what was sent I capture the request in the handler. And to keep mocks honest I generate or validate fixtures from the same schemas as the app, backed by contract tests against the real API.
