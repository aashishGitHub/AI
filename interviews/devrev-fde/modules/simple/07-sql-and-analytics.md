# Module 07 in plain English: SQL and analytics

> **Read this first**
> - **What it is for:** learning the SQL and dashboard skills the DevRev job description asks for: "Write SQL, analyze data, and build dashboards that inform customer decisions".
> - **Who it is for:** a beginner. No repo knowledge needed.
> - **Full module:** [07-sql-and-analytics.md](../07-sql-and-analytics.md). Read it after this file.

**Honesty lanes.** [P] = shipped at Couchbase. [L] = my own build. [K] = knowledge only.

- Everything here is **[L]**: my own practice work.
- The data is synthetic and seeded. Every number below is a property of the practice dataset. It is not a finding about a real system.
- The files live in the sibling repo, under [GolangExercise/offline-sync-app/analytics](../../../../../GolangExercise/offline-sync-app/analytics/).
- That folder holds 14 business-question queries in `queries/`, a seed in `seed/seed.sql`, an EXPLAIN study (`explain/`, `indexes.sql`, `EXPLAIN.md`), twelve interview questions in `QUESTIONS.md`, and a Go integration test `analytics_test.go`.
- It runs in a separate database, `fieldsync_analytics`, on Postgres 16.15.
- I re-ran the repo queries and every "Illustrative" snippet in the local container before writing the full module.
- I did not run the Go tests. They reseed the database. I read them and re-ran the SQL by hand.

---

## Phase 1: Relational foundations (joins, grouping, NULLs)

**Analogy: a class register.** The register lists every student (the left table). A LEFT JOIN keeps every student, even those with no exam score. An INNER JOIN quietly drops students who have no score.

### INNER JOIN vs LEFT JOIN

- An INNER JOIN keeps only rows with a match on both sides.
- A LEFT JOIN keeps every row from the left table. It fills the right side with NULLs when there is no match.
- My data has 200 disaster locations. 42 have never had a site assessment.
- An INNER JOIN to assessments silently drops those 42.
- If the customer asks "which locations were never assessed", the INNER JOIN answers a different question, with no error.
- First I decide which table defines the population I report on. I put that table on the left.

### NULL and counting

- NULL means unknown.
- `NULL = NULL` is not true. It is NULL. A WHERE clause treats NULL like false.
- `count(*)` counts rows.
- `count(column)` counts only rows where that column is not NULL.
- So after a LEFT JOIN I write `count(s.id)`. A location with no assessments then counts as zero, not one.
- For a NULL-safe comparison I use `IS DISTINCT FROM`. It treats two NULLs as equal.

### Typical location: mean vs median

- Question: how many assessments does a typical location have, and how many have none?
- I start from the locations table and LEFT JOIN the assessments.
- I group by location and use `count(s.id)`, so empty locations get a zero.
- Then I aggregate those counts into a mean, a median with `percentile_cont`, and a `FILTER` count of the zeros.
- On the seed: mean 10.00, median 4, and 42 locations with none.
- The mean overstates the typical location. A few busy locations pull it up.
- I would show the median and the number of empty locations. The mean is secondary.
- The grain (what one row means) is one row per location after the inner subquery.
- The join type and the count column are the two decisions that make the zeros appear.

### Why three-table funnel counts go wrong

- A location joined to its assessments, then to its photos, fans out.
- One location with 12 assessments and 8 photos each becomes 96 rows.
- Counting those rows makes a funnel that grows instead of shrinking.
- The fix: count distinct entities per stage.
- In my funnel query I collapse the photo side to one row per assessment with `SELECT DISTINCT site_assessment_id` before joining.
- On the seed, joining all three tables gives 14,530 rows for only 157 distinct locations.
- That shows how far a raw row count is from the truth.

### Backlog per consumer, and the traps

- Question: how many published events has each consumer not processed yet?
- I treat each consumer as one row from a `VALUES` list of subscriptions.
- I join the published events it is eligible for.
- I LEFT JOIN `processed_events` on both key columns.
- I count rows where `pe.event_id IS NULL`.
- An anti-join (find rows with no match) written as LEFT JOIN, and `NOT EXISTS`, give the same plan in this repo's notes.
- `NOT EXISTS` states the intent better and is NULL-safe.
- Trap 1: joining on `event_id` alone. It matches another consumer's row and hides the backlog.
- Trap 2: `NOT IN (subquery)`. It returns zero rows if the subquery has even one NULL.
- I put the condition inside `FILTER`, not `WHERE`. A healthy consumer still appears with a zero.
- On the seed: notifier 713 unprocessed, photo-processor 131, dashboard-aggregator 109.
- These belong to the synthetic data. It plants a notifier stall near the end.
- The subscription list is hard-coded in the query. If a consumer's event types change in the app, the query silently goes stale.
- I injected one NULL on purpose in a demo. `NOT IN` returned 0 rows. `NOT EXISTS` returned the correct 42.
- In the real table `location_id` is `NOT NULL`, so the trap is latent, not active. Say so honestly.

### How I know my anti-join is correct

- I check it against an independent formulation. My Go test does this.
- For each consumer, it recomputes the backlog with a separate `NOT EXISTS` query and asserts both numbers are equal.
- It also asserts that `backlog_over_1h` is not larger than `backlog`, which is not larger than `eligible`.
- The limit of that proof: both formulations share my reading of the subscription list.
- The test catches a wrong join. It does not catch a wrong business definition.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| INNER JOIN | Keep only rows that match on both sides. |
| LEFT JOIN | Keep all left rows; fill missing right values with NULL. |
| Grain | What one row of a result stands for. |
| NULL | "Unknown"; it is not equal to anything, not even another NULL. |
| Fan-out | A join that multiplies rows. |
| Anti-join | Find rows that have no match in another table. |
| FILTER | Restrict which rows feed one aggregate. |

**Say it in one breath:** I pick the grain and join type first, count `s.id` after a LEFT JOIN, and use `NOT EXISTS` for "has none".

---

## Phase 2: Window functions (row_number vs rank vs dense_rank, frames, LAG)

**Analogy: a race results board.** A window function writes each runner's rank next to their name. GROUP BY would shrink the board to one line per team. The window keeps every runner visible.

### Window function vs GROUP BY

- A window function computes a value across related rows. It keeps every input row in the output.
- GROUP BY collapses each group into one row.
- `PARTITION BY` says which rows belong together.
- `ORDER BY` inside the window says the order they are processed in.
- So I can show each worker's daily count next to their previous-day count, with no self-join.
- I cannot filter on a window function in WHERE.
- I compute it in a CTE (a named sub-query) first, then filter in the outer query.

### row_number vs rank vs dense_rank

- `row_number` gives every row a unique number. Ties are split arbitrarily unless I add a tiebreaker.
- `rank` gives tied rows the same number, then skips. Example: 1, 1, 3.
- `dense_rank` gives tied rows the same number and does not skip. Example: 1, 1, 2.
- Which is right is a business decision.
- Exactly three badges per location: `row_number` with a stated tiebreak.
- Everyone tied for a podium place included: `rank`.

### Top three assessors per location, with ties

- I count assessments per location and actor in a CTE.
- I compute all three ranking functions side by side over the same partition, to show the difference.
- The `row_number` ordering has two explicit tiebreakers: most recent assessment, then actor id. The answer is the same on every run.
- `rn <= 3` returns at most three people per location.
- `rnk <= 3` can return more, because tied rows at the boundary all stay.
- `drnk <= 3` can return the most, because it keeps the top three distinct counts.
- On the seed, "top three" returned 416 rows with `row_number`, 546 with `rank`, and 615 with `dense_rank`.
- The function I pick changes the answer size by almost 50 percent.

### Comparing with the previous working day

- I aggregate to one row per actor and day.
- I use `lag(events) OVER (PARTITION BY actor_sub ORDER BY day)` to get the previous value, then subtract.
- The first row per actor has no previous row. `lag` returns NULL, so the delta is NULL.
- I use `100.0`, not `100`, so the percentage is not integer division.
- I use `NULLIF(..., 0)` so a zero previous value does not abort with a division by zero.
- `lag` gives the previous active day, not the previous calendar day.
- On the seed, actor-07 goes from 2026-08-01 to 2026-08-03. `days_between` is 2, because the weekend has no row.

### Window frames and the default-frame bug

- A frame says which rows around the current row feed the aggregate.
- `ROWS` counts physical rows.
- `RANGE` counts values of the ORDER BY key.
- If I write only `ORDER BY`, the default frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
- Rows that tie on the ORDER BY value are peers. All of them see the same running total.
- In a four-row demo, two tied rows on day 2 both show 11 under the default frame. The explicit `ROWS` frame shows 8, then 11.
- My running-total query shows both versions: the explicit `ROWS` frame with a unique tiebreaker, and the default frame in the last column.
- On sparse data, `ROWS 6 PRECEDING` can reach back weeks, because idle days have no row.
- For a calendar week I use `RANGE BETWEEN INTERVAL '6 days' PRECEDING`, or I densify first with `generate_series`.
- I did not measure the cost of frames.
- The repo notes say one sort feeds both window nodes when `PARTITION BY` and `ORDER BY` match. That is what I would look for in EXPLAIN.
- `RANGE` with an interval offset is available from Postgres 11, per the repo notes. I did not test older versions.

### Distinct count in a running window

- Question: distinct workers ever seen, by day.
- Postgres rejects `count(DISTINCT x) OVER (...)`. The error is "DISTINCT is not implemented for window functions". I confirmed it in the container.
- Workaround: compute each worker's first-seen day, count how many workers first appeared each day, then take a running `sum`.
- Trade-off: one extra aggregation step.
- Days with no new worker have no row. Join to a `generate_series` if the customer needs a continuous line.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Window function | Computes over related rows but keeps every row. |
| PARTITION BY | Splits rows into groups for the window. |
| CTE | A named sub-query written with `WITH`. |
| rank / dense_rank | Ties share a number; rank skips after a tie, dense_rank does not. |
| Frame (ROWS / RANGE) | Which neighbouring rows feed the aggregate. |
| lag | Look at the previous row's value. |
| Peer rows | Rows that tie on the ORDER BY value. |

**Say it in one breath:** Window functions rank and compare without collapsing rows, and I give them a total order and an explicit frame.

---

## Phase 3: Percentiles and time-series bucketing (percentile_cont, date_trunc, generate_series)

**Analogy: a queue at an airport.** Most people wait five minutes. A few wait three hours. The average says "about 20 minutes", which describes nobody. The median and the slowest one percent tell the real story.

### Why median and p99, not the average

- Latency is long-tailed. A few very slow requests drag the mean away from a typical request.
- The mean also hides how bad the worst cases are.
- The median is the typical experience.
- The 99th percentile (p99) is what the slowest one percent see.
- In my sync-lag data the clients are offline-first and queue writes. The median is seconds. The tail is hours.
- One average would describe neither group.

### percentile_cont vs percentile_disc

- `percentile_cont` interpolates between the two nearest values. It can return a number not in the data.
- `percentile_disc` returns an actual observed value.
- For 1, 2, 3 and 100: the continuous median is 2.5. The discrete median is 2.
- I use continuous for durations.
- I use discrete when the answer must be a real observed value, such as an id or a category.

### Median, p90, p99 and last-14-days p99 in one pass

- I stack the three lag measures into one `samples` CTE with `UNION ALL`. Each row has a metric name, a segment and seconds.
- I group by metric and segment and call `percentile_cont(...) WITHIN GROUP (ORDER BY secs)` for each percentile.
- The `FILTER (WHERE ...)` clause goes after `WITHIN GROUP`. It limits which rows feed that one aggregate.
- That gives the all-time p99 and the last-14-days p99 side by side.
- The 14-day cutoff uses UTC wall-clock timestamps. Phase 5 explains why.
- Toy data (1, 2, 3, 100) gives 2.5, 2 and mean 26.5.
- Real sync lag on the seed: mean about 0.51 hours, median about 0.001 hours, p99 about 8.74 hours.
- The three numbers describe three different things.

### Showing quiet time buckets

- Grouping by `date_trunc` only returns buckets that have rows. An outage is invisible. No rows is not the same as zero.
- I generate every bucket with `generate_series`.
- I LEFT JOIN the events with a half-open range: `>= start AND < start + 1 hour`. A btree on the timestamp can then be used.
- I use `count(de.id)`, not `count(*)`. `count(*)` would count an empty bucket as one.
- I generate the series on `timestamp` without time zone, made with `AT TIME ZONE 'UTC'`. No hour is skipped or repeated by daylight saving.
- The seed plants an outage on 2026-08-13: six zero rows for 10:00 to 15:59 UTC.
- A plain `GROUP BY date_trunc('hour', ...)` over the same window returns only four rows. It shows no outage.

### Can I pre-aggregate p99?

- No. Percentiles do not compose. The average of per-group p99 values is not the p99 of the pooled data.
- On the seed: the average of the 25 per-actor p99 values is about 5.47 hours. The pooled p99 is about 8.74 hours. A gap of more than 3 hours.
- If I must pre-aggregate, I would store a histogram or a t-digest (a compact summary for approximate quantiles), or recompute from raw rows.
- Exact percentiles sort each group. That is O(n log n) in time and memory.
- That is fine at 50,680 rows. I did not measure larger sizes.
- At hundreds of millions of rows in a warehouse, I would move to approximate quantiles.
- The exact gap depends on how skewed the seed is. The direction of the error does not.

### Which time zone does a weekly bucket use?

- `date_trunc('week', timestamptz)` uses the session time zone. The same instant can land in different weeks for different sessions.
- I apply `AT TIME ZONE 'UTC'` first, then truncate the resulting `timestamp`. The bucket is a Monday in UTC whatever the session says.
- A related trap: `generate_series(date, date, interval)` resolves to the `timestamptz` overload. It follows the session time zone.
- So I cast the bounds to `timestamp`.
- I verified both in the container.
- My repo test runs every query under UTC and Pacific/Auckland sessions to keep it that way.
- Demo: the same instant lands in the week of 2026-06-29 under UTC. It lands in the week of 2026-07-06 in an Auckland session.
- The cost: "week" now means UTC week. For a customer in another zone, state the definition on the chart.
- My weekly p99 for the dashboard ranges from about 5.77 to 11.03 hours across 14 weeks on the seed.
- The first and last weeks are partial. The data runs from Wednesday 2026-07-01 to Monday 2026-09-28. I read no trend into it.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Median (p50) | The middle value; half are below, half above. |
| p99 | The value that 99 percent of results are under. |
| percentile_cont / disc | Interpolated percentile / an actual observed value. |
| date_trunc | Cut a timestamp down to the hour, day or week. |
| generate_series | Make a list of every time bucket, including empty ones. |
| Half-open range | `>= start AND < end`; the end is excluded. |
| t-digest | A compact structure for approximate percentiles. |

**Say it in one breath:** I report median and p99, never average a p99, and generate every bucket so outages show as zeros.

---

## Phase 4: Cohorts, funnels and sessionization (gaps and islands)

**Analogy: a school year group.** A cohort is everyone who joined in September. Retention asks how many are still at school after a term. A session is one visit to the library, and a long gap means they left and came back.

### Cohorts and retention

- A cohort is a group of users who started in the same period, such as the week of their first event.
- Retention is the share of that cohort still active some number of periods later.
- I use it to ask whether newer groups stick better than older ones.
- Always say what counts as "active" and what the denominator is.
- A cohort of three people moves a percentage by 33 points when one person leaves.

### Funnels

- A funnel counts how many entities reach each stage. Example: location opened, assessment created, photo taken.
- Conversion between stages shows where I lose them.
- Most common mistake: counting joined rows instead of distinct entities. A later stage looks bigger than an earlier one.
- Second mistake: mixing grains.
- On my seed: 200 locations lead to 158 with an assessment and 157 with a photo.
- But only 1,757 of 2,000 assessments, about 88 percent, have a photo.
- I say which grain I report.

### Sessionization with a 30-minute gap

- I use gaps and islands in three steps.
- Step 1: `lag(occurred_at)` over each actor gives the previous event time.
- Step 2: flag a row as a session start when there is no previous row, or the gap is more than 30 minutes.
- Step 3: a running sum of the flags gives the session number.
- The order includes the unique id. The order is total, and rows with equal timestamps are not peers.
- The first event has a NULL previous time. I handle it with an explicit `IS NULL` branch.
- Otherwise a NULL comparison falls into the ELSE branch, and numbering starts at zero.
- A gap of exactly 30:00 stays in the session, because I use `>` and not `>=`. A gap of 30:01 or more starts a new one.
- Always state the boundary.

### Weekly retention including empty cells

- I take each actor's first active week as the cohort.
- I build a grid of every cohort and every week offset with `generate_series`.
- I LEFT JOIN the activity onto the grid.
- The grid turns a dead cohort into a row with 0 percent. Without it, a missing row looks like missing data.
- I exclude the last partial week with a `last_complete` CTE. Counting it would make every cohort look like it churned in an unfinished week.
- Weeks are truncated after `AT TIME ZONE 'UTC'`.
- `date - date` is an integer number of days, so dividing by 7 is integer division on purpose.
- This is classic retention (active exactly n weeks later). It is not rolling retention.
- With only 25 actors, cohorts have 1 to 8 people. One person moves a cell by 12 to 100 points.

### How sensitive sessions are to the threshold

- Very sensitive. So the threshold is a product decision, not a technical one.
- On the seed: about 6,594 sessions at 15 minutes, 4,759 at 30 minutes, 2,350 at 60 minutes. I measured this in the container.
- Clock issue: my sessions use `occurred_at`, which is server time.
- An offline worker's queued day arrives as one sync burst and collapses into one session.
- For field-work sessions I would use the device timestamp from the payload.
- The cost: device clock skew.
- The counts come from synthetic data with planted offline lag and a planted outage. They show sensitivity. They are not a benchmark of anything real.
- I treat the number of sessions as a function of a parameter, never as a fact.

### Gaps and islands for consecutive days

- For consecutive days, `day - row_number()` is constant inside a streak.
- Both advance by one per row. The difference only changes when a day is skipped.
- Demo: the first three days share the island value 2026-06-30. The last two share 2026-07-02. Streaks of 3 and 2 days.
- I take one row per actor and day first (DISTINCT). `row_number` over raw events advances several times per day and breaks the arithmetic.
- I group by the constant to get the start, end and length of each streak.
- I pick the longest with `row_number` ordered by length descending, then start. A tie is broken deterministically.
- It is a calendar streak. A weekend with no events ends it. A working-day streak would need a calendar table.
- The same trick on hours finds silent runs in `queries/13_gaps_silent_hours.sql`.
- I number the empty working hours, subtract that many hours, and group by the constant.
- The seeded 6-hour outage on 2026-08-13 shows as one island of 6 silent hours.
- Limitation: restricting to working hours before numbering splits a silence that crosses 18:59 to 07:00 into two runs.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Cohort | A group that started in the same period. |
| Retention | The share of a cohort still active later. |
| Funnel | Counts of entities reaching each stage in order. |
| Sessionization | Cutting an event stream into visits by an inactivity gap. |
| Gaps and islands | Finding unbroken runs (islands) in ordered data. |
| Classic vs rolling retention | Active exactly in week n, vs active in week n or later. |
| Densify | Add rows for missing buckets so zeros show. |

**Say it in one breath:** I cut sessions with lag, a flag and a running sum, and I treat the gap as a product choice.

---

## Phase 5: Data quality (dedupe, time zones and DST, determinism)

**Analogy: counting the same parcel twice.** A parcel scanned twice at the depot still shows up as two scans. To count parcels you must agree what makes two scans the same parcel.

### Removing duplicates

- First decide what makes two rows the same logical record. That is the business key.
- Do not assume the primary key is that key.
- In my event log every row has a fresh uuid, even when it duplicates another write.
- So the logical key is the aggregate id plus the record's `updatedAt` version.
- I number rows inside each key with `row_number()` and keep the first or the latest.
- I do not delete from an audit log. I use a view, or a `CREATE TABLE AS` of the kept rows.

### Distinct writes vs outbox rows

- A logical write is the pair of aggregate id and `payload.updatedAt`.
- I number the copies with `row_number()` ordered by latest `occurred_at`, then `id`.
- `rn = 1` is distinct. `rn > 1` is a duplicate. All in one pass with `FILTER`.
- Keeping the latest copy gives the freshest publish state.
- Keeping the first would keep the original arrival time. Say which you chose and why.
- On the seed: 50,680 raw rows, 49,001 distinct writes, 1,679 duplicate rows. About 3.3 percent.
- The seed injects roughly 3 percent on purpose.
- The consumer idempotency table keys on event id. Duplicates with different ids are processed again downstream.
- That is how a customer dashboard can over-count.
- An independent `count(DISTINCT ...)` returns 50,680 and 49,001. My Go test uses it as an oracle.

### Why the time zone changes "events per day"

- A timestamp with time zone is one instant. The calendar day it belongs to depends on the zone.
- On my seed the same calendar day, 2026-07-23, holds 1,443 events by UTC date, 1,389 by Asia/Kolkata and 889 by Pacific/Auckland.
- I measured this in the container. `QUESTIONS.md` question 10 records it.
- So I pick the zone on purpose, write it into the query with `AT TIME ZONE`, and say it next to the chart.

### The daylight-saving bug with `interval '14 days'`

- Subtracting `interval '14 days'` from a `timestamptz` is calendar arithmetic in the session time zone.
- Across a daylight-saving change it is not 336 hours. The cutoff moves by an hour.
- The repo comment in the percentile query says a test running the query under two session zones caught this.
- I could not find git history for the original failing run. I rely on the comment and on my reproduction.
- The fix: convert to UTC wall-clock `timestamp` first with `AT TIME ZONE 'UTC'`, then subtract the interval. There a day is always 24 hours.
- In my reproduction the cutoff in an Auckland session is one hour later than in UTC.
- On this seed the row count in the window was the same, 6,227 rows, because no event fell in that hour.
- A boundary bug can hide until an event lands in the shifted hour.
- The seed ends on 2026-09-28. I believe New Zealand daylight time started on 2026-09-27. Verify the exact date in the tz database if it matters.

### Making a result reproducible

- Remove every source of hidden variation, then test for it.
- The seed takes randomness from `md5` of a key, never from `random()`. It does not depend on row order or plan.
- Every ranking and window has a total order with an id tiebreaker.
- The "as of" time is the data's own `max(occurred_at)`, not `now()`.
- Day and week buckets go through `AT TIME ZONE 'UTC'`.
- The Go test runs every query under UTC and Pacific/Auckland sessions and asserts the rendered results are identical.
- It also reseeds and compares fingerprints of each table before and after.
- Trade-off: the data's own maximum makes a query reproducible. In production I must substitute `now()` on purpose and say so.
- Auckland is a good test zone because it has a big offset from UTC and, as I believe, a daylight-saving change near the end of the seed window.

### Is a query that passes my invariants correct?

- No. It is consistent with the checks I wrote.
- The checks are only as good as my independent oracles.
- The dedupe test recomputes the distinct count and asserts raw equals distinct plus duplicates. That catches a broken partition or filter.
- It would not catch a wrong business key, for example if `updatedAt` is not the right version marker.
- It cannot detect an upstream bug I have not modelled.
- Say that out loud. Add a reconciliation against a source of truth when one exists.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Business key | The fields that make two rows the same real thing. |
| Dedupe | Remove duplicate copies of the same logical record. |
| DST | Daylight saving time; some days have 23 or 25 hours. |
| `AT TIME ZONE 'UTC'` | Convert a timestamp to UTC wall-clock time. |
| Deterministic | The same input always gives the same output. |
| Oracle (in a test) | An independent way to compute the expected answer. |
| Fingerprint | A short summary used to compare tables. |

**Say it in one breath:** I dedupe on the business key, fix the time zone to UTC, and remove hidden randomness.

---

## Phase 6: Performance (EXPLAIN ANALYZE, BUFFERS, indexes)

**Analogy: a library catalogue.** To find one author, you use the catalogue and walk to the shelf. Without it, you read every spine. But if you want to count every book, the catalogue does not help. You still visit every shelf.

### Index and EXPLAIN basics

- An index is a sorted structure. The database jumps to matching rows instead of reading the whole table.
- `EXPLAIN` shows the plan the planner chose.
- `EXPLAIN ANALYZE` also runs the query. It shows actual times and row counts.
- `BUFFERS` shows how many 8 kB pages were touched.
- I trust buffers more than timing. Timing moves with caches and machines.
- I look for a Seq Scan on a big table with a selective filter. That usually means a missing index.

### Does every slow query need an index?

- No. An analytical query that must read every row is a full scan whichever index I add.
- Example: a daily count over the whole event table.
- My 14 analytical queries need no index for that reason.
- Only three lookups, the kind a customer-facing screen would run, were worth indexing in my study.
- Every extra index slows writes. Add one only when a selective, repeated lookup justifies it.

### Before and after in my EXPLAIN study

- The query is `explain/01_aggregate_history.sql`: the audit trail of one aggregate, a lookup on `aggregate_id` ordered by `occurred_at`.
- Before: only the primary key on `id` and a partial index on unpublished rows existed.
- So the planner used a Seq Scan: 6.11 ms and 3,063 buffers, to return 13 rows.
- After a composite index on `(aggregate_id, occurred_at)`: a Bitmap Index Scan, 0.105 ms and 10 buffers. About 58 times faster.
- The other two lookups: actor activity went from 8.54 ms (3,063 buffers) to 0.46 ms (93 buffers), about 19 times.
- Consumer processing went from 4.32 ms (1,081 buffers) to 0.22 ms (9 buffers), about 19 times, with an Index Only Scan.
- These numbers are from one local Postgres 16.15 container, one Apple Silicon laptop, synthetic data, fully in `shared_buffers`, median of six runs.
- They are order-of-magnitude figures, not a benchmark.
- The buffer column is the clearest: 3,063 pages down to 10.

### Why the primary key did not help the consumer query

- `processed_events` has the primary key `(event_id, consumer_name)`.
- A btree can only seek on its leading column. A filter on `consumer_name` alone cannot use it. The planner chose a Seq Scan.
- The new index on `(consumer_name, processed_at)` holds both predicates.
- The query needs only `count(*)` and `max(processed_at)`, so the index alone can answer it. That is an Index Only Scan: 0.22 ms against 4.32 ms.
- The repo notes that Postgres 16 has no skip scan and that it arrived in a later release. I am not certain of that. Verify in the current docs before repeating it.
- `Heap Fetches: 0` depends on the visibility map being current. I did not control that.
- Rule: the equality column goes first, the range column second. The column order of a composite index is the whole design.

### When the planner picks bitmap + Sort over a plain index scan

- It was right here.
- With `enable_bitmapscan` off, a single run each, the plain Index Scan removed the Sort, because `occurred_at` is the second index column.
- But it was slower: 0.25 ms against 0.075 ms for the aggregate lookup. 1.22 ms against 0.42 ms for the actor lookup.
- Buffers for the actor lookup: 374 against 93.
- One actor's rows are scattered across the heap. A plain index scan revisits pages. A bitmap scan visits each page once.
- The failure mode: trusting the "no Sort" plan by instinct.
- These are single runs on a warm cache. Do not quote the ratios as constants.
- Write-side cost, not measured: `domain_events` is the transactional outbox written on every sync.
- Two more indexes mean three btrees maintained per insert, instead of one.
- My `TestIndexesChangeThePlans` test pins the plan shape, not the timing.
- Before the indexes: every plan must have a Seq Scan and no index node. After: an index plan and no Seq Scan.

### Where an index fails to help

- An index does not help when the predicate wraps the indexed column in a function. The function result is not what the btree stores.
- In EXPLAIN I check whether a condition is under `Index Cond` or under `Filter` plus `Rows Removed by Filter`.
- Measured with the study indexes present: a query for one actor and one day wrapped in `date_trunc` put only `actor_sub` in `Index Cond`.
- It filtered out 1,657 rows, touched 14 buffers, took about 0.5 ms (0.479 and 0.516 ms in two runs).
- The half-open range version put all three predicates in `Index Cond`, touched 4 buffers, took between 0.014 and 0.058 ms in the same runs.
- These are warm, single-machine runs. I take the buffers and the `Index Cond` versus `Filter` split seriously, and the milliseconds loosely.
- That is why my bucketed queries join on `>= start AND < start + interval`, never on `date_trunc(col) = bucket`.
- The partial index on unpublished rows is the other design I use.
- The relay's poll only looks at `published_at IS NULL`, so a small partial index serves it.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| EXPLAIN ANALYZE | Show the query plan and actually run it for real timings. |
| Buffers | 8 kB pages touched; a stable measure of work. |
| Seq Scan | Read the whole table. |
| Bitmap Index Scan | Find matching pages through the index, then visit each page once. |
| Index Only Scan | Answer from the index without touching the table. |
| Composite index | An index on several columns; order matters. |
| Partial index | An index on only the rows that match a condition. |
| Skip scan | Using a composite index without its leading column; verify support per version. |

**Say it in one breath:** I read the plan, add the index the plan asks for, trust buffers over milliseconds, and say what the index costs on writes.

---

## Phase 7: From a query to a dashboard that informs one decision

**Analogy: a car dashboard.** A driver does not need fifty dials. They need speed, fuel and one warning light. Each dial changes what they do next.

### What makes a dashboard useful

- A useful dashboard informs one decision. Every chart should change what the customer does next.
- I ask which decision they must make this week, and what they would do differently for each answer.
- Then I choose the fewest metrics that rank the options.
- Extra charts make the customer re-derive the ranking themselves.

### Alert on age, not only on volume

- Volume can look healthy while events are lost.
- In my seed the stuck outbox rows are well under one percent of events. A throughput chart looks normal while those rows are never delivered.
- The age of the oldest stuck row grows every day. It cannot hide in a total.
- So I alert on the oldest age and on the trend of the tail. I show the count as a size signal.

### The one decision and the first metric

- The decision: which hop of the pipeline should an engineer work on this week?
- The hops: the offline client sync path, the outbox relay, or a consumer.
- Each metric points at exactly one hop. Together they rank the options.
- The relay metric: the count of outbox rows still unpublished after more than an hour, plus the age of the oldest.
- I measure age against the data's own latest event time, so it is reproducible. In production I would use `now()` and say I substituted it.
- On the seed: 228 rows unpublished, 227 of them for more than an hour. About 0.45 percent of the 50,680 events.
- This is a planted property of the synthetic data.

### The three-metric dashboard and the ranking

- Metric 1: the weekly p99 of client sync lag.
- Metric 2: stuck outbox rows, with the age of the oldest.
- Metric 3: unprocessed events per consumer.
- One metric per hop.
- On the seed, p99 sync lag sits between about 5.77 and 11.03 hours with no upward trend.
- The clients are offline-first, so that lag is structural. Verdict: leave that hop alone.
- The relay shows 227 rows stuck over an hour. The oldest is about 2,140 hours.
- That is silent data loss, because those events never reach any consumer.
- The notifier shows 713 unprocessed events, photo-processor 131, dashboard-aggregator 109.
- The notifier number is driven by a stall in the final hours of the data.
- My ranking: relay first (silent loss). Notifier second (live and fixable by restart). Sync path last.
- I ranked by severity, not by count. The notifier count is larger.
- A customer cannot get the ranking from any one chart. The ranking itself is the deliverable.
- Every count is planted by the seed. This shows the method, not a finding about a real system.

### Did I build the dashboard?

- In this repo the dashboard is a documented design backed by three tested queries.
- It is not a deployed BI tool. Do not claim otherwise.
- Before a customer sees it, I would agree the definitions in writing.
- What "stuck" means. The one-hour threshold. Whether duplicates collapse on the business key. Which time zone the weekly bucket uses.
- I would replace the data's `max(occurred_at)` with `now()` and add a freshness stamp.
- I would check the three queries against a source of truth. A dashboard that is confidently wrong is worse than none.
- I would reconsider the index cost from Phase 6, and serve these reads from a replica or a warehouse if the outbox table is hot.
- I have not tested that setup. It is design intent, not a measured result.

### Words you'll hear

| Term | One-line meaning |
|---|---|
| Dashboard | A page of metrics meant to drive a decision. |
| Outbox | A table of events waiting to be published. |
| Relay | The process that publishes outbox rows. |
| Consumer | A service that reads published events. |
| Silent data loss | Data that never arrives, with no error shown. |
| Freshness stamp | A label showing how recent the data is. |
| Replica | A read-only copy of the database. |

**Say it in one breath:** One dashboard, one decision, three metrics that each point at one hop, ranked by severity, and I alert on age because volume can hide loss.

---

## Mix-ups to avoid

- Do not average p99 values from groups. Percentiles do not compose.
- Do not call `percentile_cont` an approximation. It is exact and sorts each group.
- Do not use `count(*)` after a LEFT JOIN when you mean "how many matched".
- Do not confuse `rank` (1, 1, 3) with `dense_rank` (1, 1, 2).
- Do not treat the seeded numbers as real findings. The stuck rows, the notifier stall, the 3 percent duplicates and the offline lag are all planted.
- Do not quote the EXPLAIN speed-ups as general. They are one container, one laptop, warm cache.

## What I built vs what I only know

**Built [L], on synthetic data in a local Postgres 16.15 container:**

- 14 business-question queries, a deterministic seed, an EXPLAIN study with three indexes.
- Twelve interview questions in `QUESTIONS.md`.
- A Go integration test that checks time-zone independence, an independent `NOT EXISTS` oracle, and plan shapes.
- A documented three-metric dashboard design backed by three tested queries.

**Shipped [P]:** nothing in this module.

**Knowledge only [K]:** approximate quantiles in a warehouse, a skip scan in later Postgres versions (verify), a replica or warehouse for the dashboard reads.

**Not built or not claimed:**

- No deployed dashboard or BI tool.
- No measurement of the write-side cost of the extra indexes.
- The DST bug is not from my own history. The repo comment records that a two-zone test caught it. I reproduced the one-hour shift but found no commit history for the original failure.
- I did not run the Go tests in the session that wrote the full module. I read them and re-ran the SQL by hand.
- No claim that a skip scan exists or does not exist in a given Postgres version. Check the current docs.
