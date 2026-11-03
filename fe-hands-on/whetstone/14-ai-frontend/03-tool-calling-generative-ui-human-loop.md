# Tool calling and generative UI: render structured outputs and keep a human in the loop
**Round:** 14 · AI-Powered Frontends · **Level:** Principal · **Time:** 20 min · **Tags:** llm · tool calling · generative ui
Source: https://whetstone-v1.vercel.app/#ai-frontend

Scenario: an assistant can call `create_invoice`, `search_orders` etc., and the UI renders the results as components and confirmations. Design it safely.

## What they're really testing
Allowlist + validation + confirmation as a security architecture, awareness of prompt injection, and that client checks are UX while the server is the authority.

## Core answer (key points)
- **Tool call = structured request** from the model (`{ name, args }`), not prose. The model only picks from what you expose.
- **Registry:** fixed map of tool name -> `{ schema, sideEffects, renderer, handler }`. Unknown name -> error state. Args validated (e.g. zod) before rendering or running.
- **Read-only tools auto-run;** tools with side effects (send, pay, delete) require explicit user approval with a human-readable preview of the exact effect and target. Allow editing params before approving.
- **Server executes** with the user's own permissions and re-validates. The client check is a UX guard, not security.
- **Audit log:** who approved what, when, the model output that proposed it.
- **Prompt injection:** content the model reads (docs, emails, pages) may carry instructions. Defense in depth: least-privilege tools, separate read vs write tools, confirmation on all writes, no unchecked model links/images, label AI content and sources.
- **Streaming tool calls:** args arrive as partial JSON. Either wait for completion, or render a skeleton/preview from a tolerant partial parser, and enable actions only after the final args validate.
- **Never** render components by arbitrary name, fetch arbitrary URLs, or execute model code.

## Mental model / flow
```
model -> tool_call{name,args}
  -> registry lookup (unknown? show error, report back to model)
  -> schema.safeParse(args) (invalid? show error, ask model to retry)
  -> sideEffects ? render preview + [Approve][Edit][Reject] : auto-run
  -> server re-validates + authorizes + executes -> result -> back to model + UI
  -> audit log entry
```

## Code sketch
```tsx
// Own sketch: typed registry and a confirmation gate
const registry = {
  search_orders: {
    schema: z.object({ status: z.enum(['open', 'shipped']), limit: z.number().int().max(50) }),
    sideEffects: false,
    View: OrdersTable,
  },
  create_invoice: {
    schema: z.object({ customerId: z.string().uuid(), amountCents: z.number().int().positive() }),
    sideEffects: true,
    View: InvoicePreview,
  },
} as const;

function ToolCall({ name, args, approve, reject }: ToolCallProps) {
  if (!Object.hasOwn(registry, name)) return <Alert>Unknown action requested.</Alert>;
  const tool = registry[name as keyof typeof registry];
  const parsed = tool.schema.safeParse(args);
  if (!parsed.success) return <Alert>Invalid parameters for {name}.</Alert>;
  const view = <tool.View {...(parsed.data as any)} />;
  if (!tool.sideEffects) return view;
  return (
    <ConfirmCard summary={describe(name, parsed.data)}>
      {view}
      <button onClick={() => approve(parsed.data)}>Approve</button>
      <button onClick={() => reject('user declined')}>Reject</button>
    </ConfirmCard>
  );
}
```

## Trade-offs & pitfalls
- Over-confirming read-only actions creates confirmation fatigue; users click through the risky one. Confirm only side effects.
- Raw JSON previews are unreadable; say "Send invoice for 12,400 INR to Acme Corp".
- `Object.hasOwn` (not `in`) avoids prototype keys like `constructor` being treated as tools.
- Undo is great for reversible actions; irreversible ones (payments, external email) need confirmation, not undo.
- Partial-JSON rendering can show wrong amounts mid-stream; never enable Approve until final validation.

## Likely follow-ups
- **How does the model get the result?** Return a tool result (success or structured error) in the next turn so it can explain or retry.
- **Rejected action?** Send the rejection reason back as the tool result; the model should not silently retry.
- **Multi-step agents?** Same gate per side-effecting step; show a plan and progress; allow cancel.
- **Where does authorization live?** Server, per call, with the user's identity; the model never holds elevated credentials.

## Say it in 60 seconds
Tool calling turns model output into structured requests, so the frontend treats it as untrusted input: a fixed registry maps allowed tool names to schemas, renderers and handlers, arguments are validated before anything renders, and unknown tools or bad args become clear error states. Read-only tools can auto-run, but anything with side effects shows a human-readable preview of exactly what will happen, with approve, edit and reject, and the server re-validates and executes with the user's own permissions and logs an audit trail. Because the model can be steered by injected instructions in content it reads, I keep tools least-privilege, split read from write, and never let it pick arbitrary components, URLs or code. Streaming args render as a skeleton and actions unlock only after final validation.
