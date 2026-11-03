# Per-company tailoring — which resume to send and what to change

The plan's data: a tailored resume gets ~4.23% interviews vs 2.07% for a generic one (Huntr, US data). Tailor the **top third only**: header line, summary and the first 3 Couchbase bullets. Never touch facts.

## How to tailor in 10 minutes (no Claude needed)
1. Open the JD. Copy its 8–10 most repeated nouns (e.g. "design systems", "RSC", "observability").
2. Choose the variant from the table below.
3. Put the 3–4 JD nouns you can honestly claim into the summary and the Skills line. Keep the same order as the JD.
4. Move the Couchbase bullet that best matches the JD to the top.
5. Export to PDF: `Aashish_Kumar_<Company>_<Role>.pdf`. Log it in your tracker.
6. With free Claude/Gemini: use prompt P1 in `06_Free_AI_Prompts.md`.

## Variant map
| Company | Role to search on careers page | Send | Level to insist on (plan Q3) | Lead bullet | Loop notes (plan Q6) |
|---|---|---|---|---|---|
| Databricks | Sr / Staff SWE – Databricks AI; Staff SWE – Fullstack (control-plane UI) | A (AI) or B (Fullstack) | Staff | LCP 22s→6–7s on a control-plane console. The Fullstack JD is "almost exactly your Capella job". | Hard coding + system design + HM |
| Databricks | AI Engineer – AI FDE; Deployment Strategist (Remote India) | C | Senior FDE | Escalations + SSE unblock + eval harness | Expects Spark depth — you have a gap, so say it honestly |
| Atlassian | Principal Frontend SWE; Senior Frontend SWE (JSM); Rovo AI teams | A | P50 min (~₹1.12Cr median), push for P60 | Design system + perf + AI UI | Frontend machine coding + frontend system design + values |
| Atlassian | Senior Principal Forward Deployed Engineer | C | P60 | Customer escalations + evals | Verify the posting first |
| Amazon | SDE III Frontend / Fullstack (AWS console teams) | A or B | **L6 only** (~₹1.36Cr). L5 lands near your band → decline. | Perf + ownership stories mapped to LPs | DSA heavy, 4–5 rounds, bar raiser. **No AI tools.** |
| Google | Senior SWE Frontend (L5) | A | **L5** (~₹1.26Cr) | Perf with waterfall-level detail | DSA x2–3, system design at L5, Googleyness. One possible AI-assisted round. |
| Microsoft | Senior SWE Frontend; Azure portal / Copilot surfaces | A | **64** (~₹98L). 63 (~₹71.5L) sits inside your band → negotiate hard. | Console perf + AI UI | Coding + design + HM |
| Salesforce | SMTS / LMTS UI, Agentforce UI | A | **LMTS** (SMTS ~₹77.3L) | AI UI + design systems | Not verified for 2026 |
| ServiceNow | Staff / Principal UI Engineer, Now Assist | A | Staff | AI UI | ⚠ Rumoured India layoffs Oct 2026 (unconfirmed) → keep as a backup |
| Adobe | Senior Computer Scientist / SDE 4 Frontend | A | Senior CS | Perf + design system | Not verified |
| Uber / Walmart Global Tech / Intuit / Rippling / LinkedIn | Senior / Staff Frontend or Fullstack | A or B | Staff where it exists | Perf | Check each careers page |
| Any "Fullstack" req | — | B | — | Go Recents backend + SSE | Lead with frontend + AI in the summary anyway |
| Any "AI Engineer / LLM apps" req | — | D | — | Eval harness + AI search | Python fluency will be probed. Say "reading + scripting", never "expert". |

## Never on any variant
- "Principal" / "Architect" as a title, "certified" for AWS, numbers from the UNVERIFIED table in the master resume.
- Couchbase-internal code, screenshots or docs in a take-home or portfolio.
