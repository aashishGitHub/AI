# Scenarios 07 — SQL & analytics

Real-time situations for [module 07](../07-sql-and-analytics.md). Each one is a customer analytics problem an FDE (Forward Deployed Engineer, the person who makes the product work inside one customer's tool estate) meets while building SQL, dashboards and proofs of value.

Lanes: **[P]** shipped at Couchbase, **[L]** my own build, **[K]** knowledge only. The SQL lives in `GolangExercise/offline-sync-app/analytics/` on a synthetic, seeded Postgres 16 dataset. No dashboard was ever deployed to a customer, and every count in the repo is planted by the seed generator, so it shows the method and not a finding about a real system. Numbers in a **Situation** are invented examples. Where I quote a seed number I say "seed". Relative links reach sibling repos, so they resolve only with the same checkout layout as my laptop. I do not paste Couchbase monorepo code.

Ladder: 🟢 scenarios 1-2, 🟡 scenarios 3-4, 🔴 scenarios 5-6.

---

## Scenario 1 — Duplicate rows inflate a metric 🟢

**Situation.** Monday 09:30. The customer's ops lead says the "writes this week" tile is about 3% higher than the field team's own tally (example). Support suspects offline devices that retry. On the practice seed the same shape appears: 50,680 raw event rows against 49,001 distinct writes.

**Level.** 🟢 Beginner.

**What's being tested.** Defining the logical key of a record (not trusting the primary key), then counting distinct entities with `row_number()` or `count(DISTINCT ...)`.

**Clarifying questions to ask first.**
1. What makes two rows "the same write" in the customer's mind: the record id plus its version, or something else?
2. Where can duplicates come from: client retries, an outbox relay publishing twice, a consumer reprocessing?
3. Does the consumer's idempotency table key on event id? A duplicate with a new event id gets processed again.
4. Should I keep the first or the latest copy of a duplicate, and why?
5. Is this table an audit log? If so I must not delete from it.

**Flow of control and data.**

```
offline device retries --> new event row (new uuid, same aggregate_id + payload.updatedAt)
domain_events --> consumers dedupe on event_id only --> duplicate counted downstream
dashboard query: row_number() OVER (PARTITION BY aggregate_id, payload->>'updatedAt' ORDER BY occurred_at DESC, id DESC)
   rn = 1 --> distinct write      rn > 1 --> duplicate row
```

**Diagnosis steps.**
1. `SELECT count(*), count(DISTINCT (aggregate_id, payload ->> 'updatedAt')) FROM domain_events` gives raw versus distinct. The gap is the duplicate count.
2. Group duplicates by `event_type` and look at `max(copies)` to see how many copies one write has.
3. Check timing between copies: seconds apart suggests client retry, hours apart suggests relay or consumer replay.
4. Check the consumer table: is the primary key `(event_id, consumer_name)`? Then duplicates with different ids are processed again.
5. Confirm the metric's definition with the customer before changing the number, and state which copy (first or latest) the dashboard keeps.

**Fix now vs fix properly.**
- Now: change the dashboard query to count `rn = 1` and tell the customer the old and new numbers and why.
- Properly: make the write idempotent at the source (a client-generated event id so a retry is the same event, or a unique constraint on the business key), and dedupe downstream on the business key. Never delete from the audit log; use a view or a `CREATE TABLE AS` of kept rows.

**How you'd test it.** An independent oracle: the dedupe query's result must equal `count(DISTINCT ...)`, and raw must equal distinct plus duplicates. In the repo, `checkDedupe` runs from `TestQueryInvariants` in `analytics_test.go`. It would not catch a wrong business key, because both formulations share my reading of the key.

**Spoken answer (60-90 seconds).**
"First I would agree what counts as the same write, because the primary key is no help: in my event log every row gets a fresh uuid even when it duplicates another write. I use the aggregate id plus the record's own updatedAt as the logical key. Then I number the rows inside each key with row_number, newest first with the id as a tiebreaker, and count rn equal to one as distinct and the rest as duplicates, all in one pass with FILTER. On my seed that gives 50,680 raw rows, 49,001 distinct writes and about 3.3 percent duplicates, and I check the answer against a separate count distinct query. I would tell the customer which copy I keep, because keeping the latest preserves the freshest publish state while keeping the first preserves arrival time. I would not delete anything from an audit log, I would use a view. The real fix is upstream: a client-generated event id so a retry is the same event. And the seed duplicates are planted, so those numbers show the method, not a real system."

**Follow-ups the interviewer will ask.**
- Why does the consumer table not catch this? It keys on event id, so a duplicate with a different id is a new event to it.
- First or latest copy? Say which and why; latest keeps freshest state, first keeps original arrival.
- Is passing my invariants proof the query is right? No, it is consistent with my checks; a wrong business key passes.

**Tie to your code.** [L] Dedupe query: [11_dedupe_latest.sql](../../../../../GolangExercise/offline-sync-app/analytics/queries/11_dedupe_latest.sql). Oracle test: [analytics_test.go](../../../../../GolangExercise/offline-sync-app/analytics/analytics_test.go). Source-side fix, a client-generated event id reused on every retry (a different project, a different pipeline): [EventId.java](../../../../../streampulse/libs/platform/src/main/java/com/streampulse/platform/domain/EventId.java). I did not trace how the FieldSync outbox ids are generated for this scenario.

---

## Scenario 2 — The funnel grows instead of shrinking 🟢

**Situation.** Tuesday 11:00. A customer's funnel slide shows 14,530 "locations with photos" against 200 locations opened (example, built from the seed's join counts). Another chart omits the locations that were never assessed entirely.

**Level.** 🟢 Beginner.

**What's being tested.** Join type (INNER versus LEFT), join fan-out, grain, and counting distinct entities per stage.

**Clarifying questions to ask first.**
1. What is the population: every location opened, or only locations that have an assessment?
2. What is the grain of each stage: locations, assessments or photos?
3. Is each stage counted by distinct entity, or by joined rows?
4. Should a location with zero assessments appear, and as what?
5. Which region or period is the customer deciding on?

**Flow of control and data.**

```
disaster_locations (200) LEFT JOIN site_assessments LEFT JOIN photos
   fan-out: one location x 12 assessments x 8 photos = 96 rows  --> count(*) is wrong
   fix: collapse photos to one row per assessment (SELECT DISTINCT site_assessment_id), count(s.id) per location,
        then count locations FILTER (WHERE sites > 0), FILTER (WHERE sites_with_photo > 0)
INNER JOIN drops the 42 never-assessed locations silently
```

**Diagnosis steps.**
1. `SELECT count(*) AS joined_rows, count(DISTINCT l.id) AS locations FROM disaster_locations l JOIN site_assessments s ON s.location_id = l.id JOIN photos p ON p.site_assessment_id = s.id`. On the seed this prints 14,530 rows for 157 distinct locations.
2. Check the join types: an INNER JOIN to assessments removes locations with none (42 on the seed).
3. Check `count(*)` versus `count(s.id)` after a LEFT JOIN: `count(*)` counts the NULL-extended row as 1.
4. Check the stage grain: at location grain the photo conversion is about 99%, but at assessment grain about 12% of assessments have no photo (seed). The story changes with the grain.
5. Verify that each later stage is less than or equal to the earlier one for every row of the result.

**Fix now vs fix properly.**
- Now: rewrite the funnel to count distinct entities per stage with a LEFT JOIN from the population table, and say the grain on the slide.
- Properly: encode the invariants as a test (locations >= with_assessment >= with_photo, conversions between 0 and 1, ALL row equals the sum of region rows) so a fan-out regression is caught before a customer sees it.

**How you'd test it.** `checkFunnel`, run from `TestQueryInvariants`, asserts the monotone stage counts, the bounds and that the ALL row equals the sum of the regions.

**Spoken answer (60-90 seconds).**
"A funnel that grows is almost always a fan-out. If I join a location to its assessments and then to its photos, one location with twelve assessments and eight photos each becomes ninety-six rows, and counting rows makes a later stage bigger than an earlier one. On my seed that join gives 14,530 rows for only 157 distinct locations. The fix is to count distinct entities per stage: I start from the locations table, LEFT JOIN assessments, collapse the photo side to one row per assessment before joining, count assessments with count of the child id so a location with none gets zero, and use FILTER to count locations that reached each stage. The join type matters too: an INNER JOIN silently drops exactly the never-assessed locations, 42 on my seed, which is probably what the customer cares about. I would also say the grain out loud, because at location grain the photo step looks almost perfect and at assessment grain about 12 percent have no photo. These counts are planted by my generator, so they show the method."

**Follow-ups the interviewer will ask.**
- `count(*)` versus `count(column)` after a LEFT JOIN? `count(*)` counts the NULL-extended row as one; `count(column)` ignores it.
- Why DISTINCT only on the photo side? Photos are the many side that multiplies rows; collapsing it to the assessment grain before the join removes the fan-out.
- How do you prove the numbers? An independent formulation, and invariants such as monotone stage counts.

**Tie to your code.** [L] Funnel query: [06_funnel_location_assessment_photo.sql](../../../../../GolangExercise/offline-sync-app/analytics/queries/06_funnel_location_assessment_photo.sql). Invariant checks: [analytics_test.go](../../../../../GolangExercise/offline-sync-app/analytics/analytics_test.go).

---

## Scenario 3 — A dashboard percentile looks better after an outage 🟡

**Situation.** Wednesday 15:00. The weekly "publish lag p99" tile dropped from 6 s to 3 s the same week the relay stalled (example). The customer asks why the tail improved while their users complained. On the seed, 227 outbox rows are stuck for over an hour, and the oldest is about 2,140 hours old.

**Level.** 🟡 Intermediate.

**What's being tested.** NULL handling and survivorship bias in percentiles: aggregates ignore NULLs, so an unfinished row can vanish from the metric. Also, percentiles do not compose.

**Clarifying questions to ask first.**
1. How is "lag" computed, and what does it return for a row that has not been published yet? (`published_at - occurred_at` is NULL.)
2. Does the query filter out unpublished rows, or does `percentile_cont` silently ignore the NULLs?
3. Is the metric computed on raw rows or from pre-aggregated per-group percentiles?
4. Should "of those published" or "of all events" be the denominator?
5. Is there a separate metric for the age of the oldest unfinished row?

**Flow of control and data.**

```
domain_events --> samples (metric, segment, secs)
   publish_lag:  WHERE published_at IS NOT NULL   --> stuck rows never enter the sample
   percentile_cont(0.99) WITHIN GROUP (ORDER BY secs)   --> NULL secs are skipped
stalled relay: more NULL rows, fewer finished rows --> p99 over survivors can look better
```

**Diagnosis steps.**
1. Count the NULL rows: `count(*) FILTER (WHERE published_at IS NULL)` per week and per event type. A spike in the outage week explains the missing tail.
2. Compare `count(*)` of all events with the sample size `n` of the percentile. If `n` fell, rows are being dropped.
3. Look at the age of the oldest unpublished row. This metric cannot hide in a total, and in the seed it is about 2,140 hours.
4. Check for averaged percentiles: the average of per-actor p99 values is about 5.47 hours against a pooled p99 of about 8.74 hours (seed). Percentiles do not compose.
5. Check the time-window cutoff: `interval '14 days'` on `timestamptz` shifts across a daylight-saving change.

**Fix now vs fix properly.**
- Now: add the missing-row count and the age of the oldest unfinished row next to the percentile, and restate the denominator on the tile.
- Properly: report "stuck" separately (count over a threshold plus the oldest age), compute percentiles on raw rows (or store a histogram or a t-digest), never average per-group percentiles, and alert on age, not only on volume.

**How you'd test it.** A fixture with a mix of published and unpublished rows asserting that the dashboard shows both the percentile and the unpublished count. In the repo, `checkBacklog` asserts the backlog against an independent `NOT EXISTS` count. A test specifically for the survivorship case is not built: [K].

**Spoken answer (60-90 seconds).**
"The tail did not get better, it got hidden. A percentile ignores NULLs, and a row that was never published has a NULL publish lag, so in my latency query I filter those rows out. When the relay stalls, the stuck rows are exactly the slowest ones, and they never enter the sample, so the p99 over the survivors can look healthy. I would verify by counting NULL rows per week and comparing the sample size with the total event count. The fix is to report the stuck rows as their own metric, a count over a one-hour threshold and the age of the oldest, because age grows every day and cannot hide in a total. On my seed that is 227 rows and about 2,140 hours, which is a planted property of the data. A second trap is averaging per-actor p99 values: on my seed that gives about 5.5 hours against a pooled p99 of about 8.7, because percentiles do not compose. So I compute from raw rows and say the denominator on the tile."

**Follow-ups the interviewer will ask.**
- `percentile_cont` versus `percentile_disc`? Continuous interpolates and may return a value not in the data (1, 2, 3, 100 gives 2.5); discrete returns an observed value (2).
- Why median and p99, not the mean? Latency is long-tailed; the mean hides both the typical and the worst case.
- What if the table is huge? Exact percentiles sort each group; at very large sizes a warehouse's approximate quantiles are an option, which I have not measured.

**Tie to your code.** [L] Percentile query with the `published_at IS NOT NULL` filter: [04_latency_percentiles.sql](../../../../../GolangExercise/offline-sync-app/analytics/queries/04_latency_percentiles.sql). The stuck-rows metric and the pitfall note: [QUESTIONS.md](../../../../../GolangExercise/offline-sync-app/analytics/QUESTIONS.md). Backlog oracle: [analytics_test.go](../../../../../GolangExercise/offline-sync-app/analytics/analytics_test.go). A survivorship-specific test: [K].

---

## Scenario 4 — The cohort query is slow after data growth 🟡

**Situation.** Thursday 10:00. The weekly retention tile refreshed in a few seconds in the demo. After six months of data (about 80 million event rows, example) it takes 3 minutes and sometimes times out (example). The customer wants it refreshed hourly.

**Level.** 🟡 Intermediate.

**What's being tested.** Knowing that an analytical query that reads every row is not fixed by an index, and choosing pre-aggregation, windowing or an offloaded copy.

**Clarifying questions to ask first.**
1. How fresh must the tile be: hourly, daily or on demand?
2. Which cohorts and how many weeks back does the decision need? Does it need all history?
3. Is the query running against the operational primary or a replica or warehouse?
4. Which plan node dominates: the scan, the `DISTINCT`, or the cohort grid?
5. Can late-arriving events change old weeks, so pre-aggregated rows would need correction?

**Flow of control and data.**

```
domain_events (all rows) --> SELECT DISTINCT actor_sub, week --> cohort_week = min(week) per actor
   --> grid: generate_series per cohort x weeks_since_start --> LEFT JOIN activity --> retention %
growth: scans and de-duplicates every event row on each refresh
fix: maintain actor_week(actor_sub, week) incrementally; the query reads that small table
```

**Diagnosis steps.**
1. `EXPLAIN (ANALYZE, BUFFERS)` on the full query. Read the node that dominates: a Seq Scan on events with a large sort or hash aggregate for the `DISTINCT`.
2. Check buffers touched. A full-table analytic reads every page whatever index exists.
3. Check whether the cohort grid is large. It is cohorts times weeks, usually tiny compared with the event scan.
4. Check the load on the operational database: is the dashboard competing with writes on the outbox table?
5. Check how partial weeks are handled: the query excludes the last incomplete week, so freshness is bounded to complete weeks.

**Fix now vs fix properly.**
- Now: limit the lookback to the weeks the decision needs, and run the query on a replica or off-peak.
- Properly: a small pre-aggregated `actor_week` table updated incrementally (with a rule for late data), or a materialized view refreshed on a schedule, or serve it from a warehouse. Extra indexes on the operational events table cost every write, and I did not measure that cost.

**How you'd test it.** Run the aggregated version and the raw version over the seed and assert identical retention rows. In the repo, `checkRetention` asserts invariants on the raw query. The pre-aggregated table and its equivalence test are not built: [K]. I have not measured this query on large data; the practice seed has about 50,680 events.

**Spoken answer (60-90 seconds).**
"I would first read the plan, not guess. My cohort query takes every distinct actor and week from the whole events table, takes the first week as the cohort, then builds a grid of every cohort and week offset and left joins the activity onto it. The grid is small. The cost is the full scan and the de-duplication over all events, and no index fixes that because the query has to read every row. My EXPLAIN study makes the same point for my analytical queries: only the selective lookups were worth indexing. So the fix is to stop re-reading history on every refresh. I would keep a small actor-by-week table updated incrementally, or a materialized view refreshed on a schedule, and run it off the primary. The thing to decide with the customer is late data: if events can arrive for old weeks, the pre-aggregated rows need a correction rule. I should be clear that I have only run this on a synthetic seed of about fifty thousand events, so any timing at eighty million rows is an expectation, not a measurement."

**Follow-ups the interviewer will ask.**
- Why exclude the last partial week? Counting it would make every cohort look like it churned in a week that has not finished.
- Classic versus rolling retention? Mine is classic (active exactly n weeks later); say which you report.
- With 25 actors, can I read a trend? No; cohorts of 1 to 8 people move a cell by 12 to 100 points.

**Tie to your code.** [L] Cohort query: [07_weekly_retention_cohort.sql](../../../../../GolangExercise/offline-sync-app/analytics/queries/07_weekly_retention_cohort.sql). EXPLAIN method and which queries need no index: [EXPLAIN.md](../../../../../GolangExercise/offline-sync-app/analytics/EXPLAIN.md). Incremental pre-aggregation: [K], not built.

---

## Scenario 5 — Two dashboards disagree on "events per day" 🔴

**Situation.** Friday 09:00. The customer's finance view shows 1,443 events for 2026-07-23 and the Auckland ops view shows 889 for the same date (example; these are the seed counts by UTC and Pacific/Auckland). A "last 14 days" percentile also moves by one row depending on who runs it.

**Level.** 🔴 Senior.

**What's being tested.** Time zone and daylight-saving correctness in bucketing, and making results reproducible and independent of session settings.

**Clarifying questions to ask first.**
1. Which time zone defines a "day" for this customer, and does everyone agree?
2. Is the column a `timestamptz` (an instant) or a local `timestamp`? Where is the conversion done?
3. Is the session time zone set consistently by the BI tool and by the database role?
4. Does the window cross a daylight-saving change in any zone involved?
5. Is `now()` used, or the data's own latest timestamp (reproducible)?

**Flow of control and data.**

```
timestamptz instant --> day bucket depends on the zone you look from
date_trunc('week', timestamptz) --> uses the SESSION zone --> same instant, different week
fix: occurred_at AT TIME ZONE 'UTC' first, then date_trunc, then cast; state the zone on the chart
interval '14 days' on timestamptz = calendar arithmetic in the session zone (not 336 hours across a DST change)
```

**Diagnosis steps.**
1. Run the same query under `SET TIME ZONE 'UTC'` and `SET TIME ZONE 'Pacific/Auckland'` and diff the output. Any difference means a session-dependent expression.
2. Check each bucketing expression: is `AT TIME ZONE 'UTC'` applied before `date_trunc`?
3. Check `generate_series(date, date, interval)`: it resolves to the `timestamptz` overload and follows the session zone. Cast the bounds to `timestamp`.
4. Compute the cutoff both ways, `- interval '14 days'` and `- interval '336 hours'`, under an Auckland session. They differ by one hour across a daylight-saving boundary.
5. Count the rows in the window under each zone. Equal counts can still hide a bug until an event lands in the shifted hour.

**Fix now vs fix properly.**
- Now: pick one zone per tile, write it on the chart, and put `AT TIME ZONE` in the query.
- Properly: do bucketing on UTC wall-clock `timestamp`s, use the data's own latest timestamp for "as of" (and substitute `now()` deliberately in production), give every ranking a total order, and run every query under two session zones in CI and assert identical output.

**How you'd test it.** `TestQueryResultsDoNotDependOnSessionTimeZone` renders every query file under UTC and Pacific/Auckland sessions and asserts identical results. `TestSeedIsDeterministic` and `TestSeedShape` pin the data. I could not find git history for the original daylight-saving failure, so I rely on the code comment and my reproduction, and I do not claim it from my own history.

**Spoken answer (60-90 seconds).**
"A timestamp with time zone is one instant, but the calendar day it belongs to depends on the zone you look from. On my seed the same date, 2026-07-23, holds 1,443 events by UTC date, 1,389 by Asia/Kolkata and 889 by Pacific/Auckland, so both dashboards can be right. I would agree one zone with the customer, write it on the chart, and put it in the query. The part that bites is that date_trunc on a timestamptz uses the session time zone, so the same instant can fall into different weeks depending on how the BI tool is configured. I convert to UTC first with AT TIME ZONE and truncate that. Subtracting 14 days from a timestamptz is calendar arithmetic in the session zone, so across a daylight-saving change the cutoff moves by an hour; I do the subtraction on the UTC timestamp. To keep this from regressing, my test runs every query under a UTC session and an Auckland session and asserts the results are identical. I verified these in a local container, and the Auckland daylight-saving date is something I would confirm in the tz database."

**Follow-ups the interviewer will ask.**
- Why compare UTC with Auckland? A large offset and a daylight-saving change near the end of the seed window make it likely to expose a session-dependent expression.
- Does passing the test prove correctness? It proves independence from the session zone, not that the business definition is right.
- What is the seed's reproducibility rule? Randomness comes from `md5` of a key, never `random()`, so it does not depend on row order or plan.

**Tie to your code.** [L] UTC conversion in the percentile cutoff: [04_latency_percentiles.sql](../../../../../GolangExercise/offline-sync-app/analytics/queries/04_latency_percentiles.sql). Two-zone test: [analytics_test.go](../../../../../GolangExercise/offline-sync-app/analytics/analytics_test.go). Zone counts and pitfalls: [QUESTIONS.md](../../../../../GolangExercise/offline-sync-app/analytics/QUESTIONS.md).

---

## Scenario 6 — The dashboard says backlog is zero but a consumer is stalled 🔴

**Situation.** Monday 08:00. The "unprocessed events per consumer" tile shows 0 for `notifier` while customers report no notifications for 14 hours (example). The oldest unprocessed notifier event, checked by hand, is 14 hours old (example). On the seed, the notifier legitimately shows 713 unprocessed events.

**Level.** 🔴 Senior.

**What's being tested.** Anti-join correctness (`NOT IN` versus `NOT EXISTS`, join keys), where a filter belongs, and verifying a metric against an independent oracle instead of trusting it.

**Clarifying questions to ask first.**
1. What changed recently: a schema migration that made a column nullable, a new consumer, a renamed event type?
2. How is the consumer's event list defined, and could it be stale? (It is hard-coded in my query.)
3. Does the join to processed events use both key columns (`event_id` and `consumer_name`)?
4. Is the condition in `FILTER` or in `WHERE`? In `WHERE` a healthy or empty consumer can disappear from the result.
5. What is the independent check: a direct `NOT EXISTS` count, or the consumer's own lag?

**Flow of control and data.**

```
subscriptions (consumer, event_type) JOIN domain_events (published) LEFT JOIN processed_events
      ON event_id AND consumer_name  --> count rows WHERE pe.event_id IS NULL (as FILTER) --> backlog
traps:  join on event_id only --> another consumer's row hides the backlog
        NOT IN (subquery with a NULL) --> returns zero rows
        condition in WHERE --> consumer row vanishes instead of showing 0
```

**Diagnosis steps.**
1. Ground truth by hand: `SELECT count(*) FROM domain_events de WHERE de.event_type = 'photo.upserted' AND de.published_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM processed_events pe WHERE pe.event_id = de.id AND pe.consumer_name = 'notifier')`.
2. Compare it with the dashboard query's number. A mismatch confirms the metric is wrong, not the consumer.
3. Read the join keys: both `event_id` and `consumer_name` must be in the `ON` clause.
4. Search for `NOT IN (subquery)`. If the subquery column became nullable after a migration, one NULL makes the whole result empty. In my repo `location_id` is `NOT NULL`, so that trap is latent, and the scenario's migration is a hypothetical.
5. Check the hard-coded subscription list against the application's real subscriptions.
6. Check `max(processed_at)` for the notifier and its processing rate in the last hour to see the stall directly.

**Fix now vs fix properly.**
- Now: correct the query (`NOT EXISTS` or a LEFT JOIN on both keys, condition inside `FILTER`) and restart or fix the stalled consumer.
- Properly: keep an independent oracle in the test suite, derive the subscription list from the application's registry instead of hard-coding it, and alert on the age of the oldest unprocessed event per consumer.

**How you'd test it.** `checkBacklog` recomputes each consumer's backlog with a separate `NOT EXISTS` query and asserts equality, and asserts `backlog_over_1h` is at most `backlog`, which is at most `eligible`. It catches a wrong join but not a wrong business definition, and it does not detect a stale hard-coded subscription list.

**Spoken answer (60-90 seconds).**
"A backlog of zero while customers see nothing is the dangerous kind of wrong, so I would trust the consumer's age before the tile. First I compute the real backlog by hand with NOT EXISTS against the processed table, filtered on both the event id and the consumer name, and compare it with the dashboard. If they differ, the metric is broken. In my query each consumer is one row from a subscriptions list, I join the published events it is eligible for, LEFT JOIN the processed table on both key columns, and count rows where the processed side is NULL inside a FILTER, so a healthy consumer shows a zero instead of vanishing. The failure modes I know are joining on event id alone, which lets another consumer's row hide the backlog; NOT IN with a subquery that contains a NULL, which returns no rows; and a hard-coded subscription list that has gone stale. In my repo the NOT IN trap is latent because the column is NOT NULL, and my Go test recomputes the backlog independently. That test would catch a wrong join but not a stale list, so I would add the oldest-event-age alert."

**Follow-ups the interviewer will ask.**
- `LEFT JOIN ... IS NULL` versus `NOT EXISTS`? Same plan in my notes (a hash anti join); `NOT EXISTS` states the intent and is NULL-safe.
- Why alert on age and not volume? Volume can look healthy while a few events are never delivered; age grows every day.
- Can you count distinct values in a running window? No, Postgres rejects `count(DISTINCT x) OVER (...)`; compute first-seen per key and take a running sum.

**Tie to your code.** [L] Backlog anti-join: [09_outbox_backlog_consumer_lag.sql](../../../../../GolangExercise/offline-sync-app/analytics/queries/09_outbox_backlog_consumer_lag.sql). Independent `NOT EXISTS` oracle: [analytics_test.go](../../../../../GolangExercise/offline-sync-app/analytics/analytics_test.go). Index design for these reads and its cost: [EXPLAIN.md](../../../../../GolangExercise/offline-sync-app/analytics/EXPLAIN.md) and [indexes.sql](../../../../../GolangExercise/offline-sync-app/analytics/indexes.sql). A subscription list derived from the application registry, and the age alert: [K], not built.
