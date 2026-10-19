# Thu Sep 3 — Cloud · SD (Core 90m)

Track: **Cloud** (per Spike-First schedule). Topic picked autonomously: **AWS High Availability — ELB + Auto Scaling + Multi-AZ**. Reason: not yet covered in Wk1–4 outline (IAM/VPC/Lambda was covered); this is the natural next AWS SAA block and it's a favorite Staff-level system design building block.

## 1. Core concepts (30m read + notes)

**Elastic Load Balancer (ELB) types**
- ALB (Layer 7): HTTP/HTTPS, path/host-based routing, WebSockets. Use for microservices, API gateways.
- NLB (Layer 4): TCP/UDP, ultra-low latency, static IP. Use for gRPC, non-HTTP protocols.
- Both are inherently multi-AZ — this is the HA anchor.

**Auto Scaling Group (ASG)**
- Scales EC2 count by policy: target tracking (e.g. CPU 60%), step scaling, scheduled.
- Health checks: EC2 status + ELB health check. Unhealthy instance → terminated → replaced.
- Spans multiple AZs → survives a full AZ outage.

**Multi-AZ pattern**
- Minimum 2 AZs, ideally 3, for quorum-based failover (matters for RDS Multi-AZ, DynamoDB, etc).
- Stateless app tier in ASG behind ELB; state pushed to RDS/ElastiCache/S3, not local disk.

## 2. Trade-offs (write these out — this is the "artifact")

| Decision | Option A | Option B | Trade-off |
|---|---|---|---|
| Load balancer | ALB | NLB | ALB = smarter routing, higher latency. NLB = raw speed, dumb routing. |
| Scaling policy | Target tracking | Step scaling | Target tracking = simpler, reactive. Step = precise control, more ops overhead. |
| AZ count | 2 | 3 | 2 = cheaper, no quorum safety. 3 = quorum-safe, costs more. |
| State handling | Sticky sessions | Externalized session (Redis) | Sticky = simple, breaks on instance loss. Externalized = resilient, extra hop. |

## 3. Distributed SD tie-in (10m)

Same HA pattern is the answer skeleton for "design a scalable web service":
Client → DNS (Route 53) → ALB (multi-AZ) → ASG (stateless app tier) → cache (ElastiCache) → DB (RDS Multi-AZ or Aurora).
This is your default first-30-seconds answer in any system design interview — memorize the shape, then customize per question (read-heavy → add cache/CDN, write-heavy → shard/queue).

## 4. Self-check (testable — answer without looking back)

1. Why does an ASG need at least 2 AZs, not 1?
2. What happens when an ELB health check fails on an instance mid-request?
3. ALB vs NLB — which for a gRPC backend, and why?
4. Where does session state live if you're using 3+ app instances behind an ALB?

## Ships today
This file = the "sketch/notes" artifact for Thursday.

## Next session note
Fri = Mock (behavioral ↔ decomposition, alternating — check which one is due). Sat = capstone deep build.
