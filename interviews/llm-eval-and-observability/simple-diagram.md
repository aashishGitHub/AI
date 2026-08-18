# LLM Eval & Observability — Simple Diagram

> Start here. Two diagrams: the bare mental model first, then the same flow with concrete tools.

---

## 1. Simple mental model

The whole topic is **two feedback loops around a deploy gate.** Offline eval decides *whether a change ships*; online eval decides *whether what shipped is still good*.

```mermaid
flowchart TB
    CH["Change<br/>prompt · model · RAG config · corpus"]
    OFF["Offline eval<br/>golden dataset + scorers"]
    GATE{"Regression gate<br/>pass threshold?"}
    PROD["Production<br/>live traffic"]
    ON["Online eval + observability<br/>traces · sampled judging · user signals"]
    DRIFT["Drift / regression<br/>detected"]

    CH -->|"1 propose change"| OFF
    OFF -->|"2 score vs golden set"| GATE
    GATE -->|"3a fail: block"| CH
    GATE -->|"3b pass: deploy"| PROD
    PROD -->|"4 emit traces + signals"| ON
    ON -->|"5 quality drop?"| DRIFT
    DRIFT -->|"6 file new failing cases"| CH
    ON -.->|"6' harvest hard cases"| OFF

    style CH fill:#fed7aa,stroke:#ea580c
    style OFF fill:#fef9c3,stroke:#ca8a04
    style GATE fill:#fef9c3,stroke:#ca8a04
    style PROD fill:#dcfce7,stroke:#16a34a
    style ON fill:#e0e7ff,stroke:#4338ca
    style DRIFT fill:#fee2e2,stroke:#dc2626
```

### The 6 components to remember

| Component | Job (one line) |
|---|---|
| Change | Any edit that can move quality: prompt, model version, RAG params (chunking, K, re-ranker), or the corpus. |
| Golden dataset | The fixed set of cases with expectations that offline eval scores against. |
| Scorers | Deterministic/rule checks + model-graded (LLM-as-judge) + RAG metrics that turn an output into a number. |
| Regression gate | The CI threshold that blocks a merge/deploy when scores drop. |
| Online eval + observability | Traces, sampled live judging, and implicit user signals on real traffic. |
| Drift detector | Alerts when input, quality, or cost moves beyond a baseline. |

### The one idea that ties it together

**Offline eval is a *gate* (pre-deploy, on a fixed golden set, cheap enough to block CI); online eval is a *monitor* (post-deploy, on sampled real traffic, catching what the golden set never contained).** You need both because the golden set can be green while production quietly rots — and production signals only tell you *after* users were affected. The loop closes when production's hard cases are harvested back into the golden set.

---

## 2. Detailed diagram (concrete, defensible tooling)

These are *defensible* picks that match your stack and the tutor-prompt's vetted tools — not the only valid choices.

```mermaid
flowchart TB
    subgraph OFFLINE["OFFLINE — pre-deploy gate"]
        direction TB
        DEV["Engineer changes prompt/model/RAG"]
        PF["promptfoo harness<br/>providers × prompts × tests"]
        GOLD[("Golden dataset<br/>cases + expectations")]
        RULE["Rule/deterministic checks<br/>regex · JSON schema · contains"]
        JUDGE["LLM-as-judge / G-Eval<br/>+ Ragas RAG metrics"]
        CI{"CI regression gate<br/>score ≥ threshold?"}
        DEV --> PF
        GOLD --> PF
        PF --> RULE
        PF --> JUDGE
        RULE --> CI
        JUDGE --> CI
    end

    DEPLOY["Deploy<br/>versioned prompt + model pin"]
    CI -->|"pass"| DEPLOY
    CI -->|"fail"| DEV

    subgraph ONLINE["ONLINE — production monitor"]
        direction TB
        APP["LLM feature in prod<br/>SSE streaming answers"]
        TRACE["Tracing / observability<br/>OpenTelemetry + LLM tool"]
        SAMPLE["Sampled async judging<br/>e.g. 1–5% of traffic"]
        SIGNAL["Implicit user signals<br/>thumbs · copy · retry · abandon"]
        ALERT["Drift & cost alerts"]
        APP --> TRACE
        TRACE --> SAMPLE
        APP --> SIGNAL
        SAMPLE --> ALERT
        SIGNAL --> ALERT
    end

    DEPLOY --> APP
    ALERT -.->|"harvest hard cases"| GOLD

    style OFFLINE fill:#fffbeb,stroke:#ca8a04
    style ONLINE fill:#eef2ff,stroke:#4338ca
    style GOLD fill:#dbeafe,stroke:#1d4ed8
    style CI fill:#fef9c3,stroke:#ca8a04
    style DEPLOY fill:#dcfce7,stroke:#16a34a
    style APP fill:#dcfce7,stroke:#16a34a
    style ALERT fill:#fee2e2,stroke:#dc2626
```

### Service cheat-sheet

| Concept | Tool (defensible pick) | One-line why |
|---|---|---|
| Eval harness / gate | **promptfoo** | Declarative providers × prompts × tests × assertions; runs local + CI; has model-graded/G-Eval built in. *(Verify current assertion types in its docs.)* |
| RAG-specific metrics | **Ragas** | Purpose-built RAG metrics (faithfulness, context precision/recall, answer relevancy). *(Metric names have changed across versions — verify current docs.)* |
| Model-graded scoring | **LLM-as-judge / G-Eval** | Scores open-ended quality no rule can express; G-Eval adds chain-of-thought + criteria decomposition. |
| Deterministic checks | Language-native asserts (regex, JSON-schema, string match) | Free, instant, non-flaky — the first line of defense; some criteria *must* be rule-based (see [`answers.md`](answers.md) Q11). |
| Tracing / observability | **OpenTelemetry** + an LLM-aware tool (e.g. Langfuse, Arize Phoenix, LangSmith) | Span-level latency/token/cost per request; ties a user complaint to a specific trace. *(Confirm each tool's current features.)* |
| CI | GitHub Actions (or your CI) | Where the regression gate runs on PRs / nightly. |
| Case study baseline | Ask AI's cosine-sim (`ada-002`) + GPT-4 classifier sheet | The real, shipped eval this topic upgrades — see [`answers.md`](answers.md) Q34. |

### Protocols / concepts worth naming

- **Pointwise vs pairwise judging** — score one output on a rubric, vs pick the better of two (A/B).
- **Reference-based vs reference-free** — compare to a gold answer, vs judge the output standalone (forced when no gold exists).
- **Regression gate** — CI fails the build when an aggregate score drops below a baseline/threshold.
- **Sampling** — judge only a fraction of live traffic to bound online-eval cost.
- **Drift** — statistically significant movement in inputs, output quality, or cost vs a baseline window.
- **Golden-set harvesting** — promoting real production failures into the offline dataset so they're regression-tested forever.

> Cross-links: retrieval details live in `rag-hybrid-search`; store/index choices in `vector-databases`; agent-specific eval in `agentic-rag-and-mcp`. See [`../ROADMAP.md`](../ROADMAP.md).
