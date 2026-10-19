# Plan — Deliver `CERES-Go-AWS-Plan.md` (PRD + Architecture for a Go + AWS port)

## Context
The user wants to rebuild the CERES offline-first flood-damage app on a **Go + AWS serverless** stack with a
**React (Vite) PWA**, in a **new project**. Deliverable this round = **one self-contained Markdown document**
(PRD + full architecture + implementation plan + starter snippets) they can drop into a fresh repo and start.
No code is built here; the doc is the artifact. It ports the existing app's proven model (offline outbox,
idempotent GUID upsert, LWW, geotagged photos, ≤10 rule, per-location dashboard, auth-gates-sync-not-capture).

## Locked decisions
- **Compute:** AWS Lambda (Go, `provided.al2023`, arm64) behind **API Gateway HTTP API**. Single "Lambda-lith"
  running a **chi** router via `aws-lambda-go-api-proxy` → same handler runs locally as a plain HTTP server
  (dev/prod parity). Per-route Lambdas noted as alternative.
- **Database:** **Aurora Serverless v2 (PostgreSQL)**; access via **pgx + sqlc** (type-safe). Migrations via
  **golang-migrate**. **RDS Proxy** for Lambda connection pooling; Aurora in private subnets.
- **Auth (industry standard):** **Amazon Cognito user pool** + **API Gateway JWT authorizer**. Client uses
  **AWS Amplify Auth** (register/login/refresh, hosted or custom UI); Lambda reads `sub`/`email` from the
  authorizer claims — no password code owned. Offline-tolerant (cached tokens, refresh on reconnect).
- **Photos:** **S3** via **presigned PUT URLs** (client uploads directly, dodging Lambda payload limits);
  private bucket + **CloudFront (OAC)** for serving; geotag metadata + object key in Postgres.
- **Frontend:** **React + Vite + TypeScript PWA** — Dexie + `dexie-react-hooks` (≈ Angular liveQuery), a sync
  store (Zustand), `vite-plugin-pwa`/Workbox service worker, canvas watermarking, Amplify Auth. Hosted on
  **S3 + CloudFront**. (Next.js explicitly rejected — no SSR/SEO value for an auth-gated offline field tool.)
- **IaC:** **Terraform** (VPC, Aurora, RDS Proxy, Cognito, API Gateway, Lambda, S3×2, CloudFront, IAM, Secrets).
- **Testing:** Go `testing` + `testify` + **gomock** (mirrors the Moq suite: sync applied/ignored-stale/
  conflict, idempotency, ≤10 rule). Optional `dockertest` for repo integration. Frontend: manual/e2e.

## Target architecture (serverless)
```
React PWA (S3+CloudFront) ──HTTPS──> API Gateway (HTTP API + Cognito JWT authorizer)
   IndexedDB outbox                         │ invoke
   sync engine ─ presign ─> S3 (photos) <───┤  Go Lambda-lith (chi via lambda-go-api-proxy)
   Amplify Auth ─> Cognito                  │  → RDS Proxy → Aurora Serverless v2 (Postgres)
```
Design invariants carried over: client-GUID PK → idempotent upsert; `updated_at` → Last-Write-Wins;
outbox + retry/backoff; auth gates **sync**, not **capture**; server stamps `created_by` from JWT `sub`.

## Deliverable: `CERES-Go-AWS-Plan.md` (repo root) — section outline
1. **Overview & goals** — what we're porting and why serverless.
2. **PRD** — problem, users/roles, user stories, functional + non-functional requirements, offline constraint,
   acceptance criteria, out-of-scope.
3. **Domain model** — DisasterLocation → Farm(SiteAssessment) → Photo (+ condition Good/Moderate/Bad),
   Postgres DDL, GUID PKs, `updated_at`, `created_by`.
4. **Architecture** — the diagram above + component responsibilities; VPC/networking; RDS Proxy rationale;
   presigned-upload flow; CloudFront/OAC; sequence diagrams (sync, photo upload, login).
5. **API contract** — routes (`POST /api/sync`, GET locations/{id}, GET sites/{id},
   `POST /api/sites/{id}/photos/presign` + confirm, `GET /health`), request/response JSON, status codes.
6. **Auth** — Cognito user pool + app client, API Gateway JWT authorizer, Amplify Auth on the client, the
   offline token lifecycle, "auth gates sync not capture", attribution via `sub`.
7. **Offline-first frontend** — Dexie schema, sync engine (drain/retry/LWW/idempotent, pull-on-login),
   service worker, photo watermark, per-location dashboard (pie), guard (offline allows capture).
8. **Go backend** — repo layout, chi-lith + lambda adapter, sync service + interfaces, sqlc/pgx, migrations,
   the ≤10 rule, error→HTTP mapping.
9. **Infrastructure (Terraform)** — module list, key resources, secrets, environments.
10. **Local development** — docker-compose (Postgres + LocalStack S3 + cognito-local), run chi server, Makefile.
11. **CI/CD** — GitHub Actions (test Go, build web, `terraform apply`, deploy Lambda, S3 sync + CF invalidate).
12. **Testing strategy** — gomock suites mirroring the Moq tests; what to assert.
13. **Security** — least-priv IAM, private S3+OAC, RDS Proxy + Secrets Manager, WAF, CORS.
14. **Cost notes** — Aurora Serverless v2 min-ACU floor (flag it), Lambda/API GW/S3/CloudFront, Cognito free
     tier; a cheaper variant (RDS t4g.micro or DynamoDB) called out.
15. **.NET/Angular → Go/AWS mapping table** — each existing piece → its new equivalent (e.g., `SyncService.cs`
     → `internal/sync`, EF Core → sqlc, `[Authorize]` → Cognito authorizer, `wwwroot/uploads` → S3 presigned).
16. **Phased roadmap** — Phase 0 scaffolding → 1 auth → 2 sync/API+DB → 3 photos/S3 → 4 dashboard →
     5 IaC/deploy → 6 hardening; each concept-ready with a milestone.
17. **Starter snippets** — chi-lith `main.go` + lambda entry, a sqlc query + Go sync upsert, a Terraform
     skeleton (API GW + Lambda + Cognito authorizer), the React sync store + Dexie schema, `POST /sync` JSON.

## Verification (of the deliverable)
- The `.md` is self-contained: a reader can scaffold the repo layout, run `docker-compose` for local dev, and
  follow the phased roadmap without referring back to the .NET repo.
- Every functional requirement in the PRD maps to an API route + a frontend behavior + a Terraform resource.
- The mapping table covers every major .NET/Angular component.
- Offline invariants (idempotency, LWW, auth-gates-sync) are stated with the exact mechanism in Go/AWS terms.

## Post-approval
On approval I'll write `CERES-Go-AWS-Plan.md` at the repo root with all sections above, including the starter
code snippets and mermaid/ascii diagrams, ready to copy into a new project.
