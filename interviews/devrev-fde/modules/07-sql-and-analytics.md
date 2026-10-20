# Module 07 — SQL & analytics

> This module is my SQL and analytics practice for the DevRev Forward Deployed Engineer interview, whose job description says "Write SQL, analyze data, and build dashboards that inform customer decisions". Everything lives under `GolangExercise/offline-sync-app/analytics/`: fourteen business-question queries in `queries/`, a deterministic seed in `seed/seed.sql`, an EXPLAIN study in `explain/`, `indexes.sql` and `EXPLAIN.md`, twelve interview questions in `QUESTIONS.md`, and a Go integration test in `analytics_test.go`. The schema comes from migrations `000001_init_schema.up.sql` and `000002_add_domain_events.up.sql` and runs in a separate database, `fieldsync_analytics`, on Postgres 16.15. Every item is lane [L], my own work, and the data is synthetic and seeded, so every number below is a property of the practice dataset and not a finding about a real system. I re-ran the repo queries and every "Illustrative" snippet in the local container before writing this guide.

## Phases at a glance

| Phase | One-sentence purpose | Main code |
|---|---|---|
| 1. Relational foundations (joins, grouping, NULLs) | Get the grain and the NULL rules right so a count means what the customer thinks it means. | `queries/06_funnel_location_assessment_photo.sql`, `queries/09_outbox_backlog_consumer_lag.sql`, `QUESTIONS.md` Q4-Q5 |
| 2. Window functions | Rank, compare to the previous row and compute running totals without collapsing rows. | `queries/02_top3_per_group_ties.sql`, `queries/01_moving_avg_per_actor.sql`, `queries/08_running_total_share.sql` |
| 3. Percentiles and time-series bucketing | Describe skewed latency honestly and make quiet time buckets visible. | `queries/04_latency_percentiles.sql`, `queries/13_gaps_silent_hours.sql` |
| 4. Cohorts, funnels and sessionization | Turn an event stream into sessions, retention triangles and stage conversion with gaps and islands. | `queries/05_*.sql`, `queries/07_*.sql`, `queries/06_*.sql`, `queries/14_*.sql` |
| 5. Data quality | Dedupe on a business key, keep time zones out of the answer and make results reproducible. | `queries/11_dedupe_latest.sql`, `seed/seed.sql`, `analytics_test.go` |
| 6. Performance | Read a plan, add the index the plan asks for and say what it costs. | `EXPLAIN.md`, `indexes.sql`, `explain/*.sql` |
| 7. From a query to a dashboard that informs one decision | Pick one decision and the minimum metrics that rank the options. | `QUESTIONS.md` final section, `queries/09_*.sql` |

## Phase 1 — Relational foundations (joins, grouping, NULLs)

### 🟢 Beginner

**Q:** What is the difference between an INNER JOIN and a LEFT JOIN, and why does it matter for a customer question?

**A:** An INNER JOIN keeps only the rows that have a match on both sides, and a LEFT JOIN keeps every row from the left table and fills the right side with NULLs when there is no match. In my dataset there are 200 disaster locations and 42 of them have never had a site assessment, so an INNER JOIN to assessments would silently drop exactly those 42. If the customer asks "which locations were never assessed", the INNER JOIN answers a different question without any error. I always decide first which table defines the population I am reporting on, and I put that table on the left.

**Q:** What does NULL do in a comparison, and how is `count(*)` different from `count(column)`?

**A:** NULL means unknown, so `NULL = NULL` is not true, it is NULL, and a WHERE clause treats NULL like false. `count(*)` counts rows, while `count(column)` counts only rows where that column is not NULL. That difference is the reason I write `count(s.id)` after a LEFT JOIN: the NULL-extended row for a location with no assessments counts as zero instead of one. When I need a NULL-safe comparison I use `IS DISTINCT FROM`, which treats two NULLs as equal.

### 🟡 Intermediate

**Q:** How many assessments does a typical location have, how many have none, and is the average misleading?

**A:** I start from the locations table, LEFT JOIN the assessments, group by location and use `count(s.id)` so empty locations get a zero. Then I aggregate those per-location counts into a mean, a median with `percentile_cont`, and a `FILTER` count of the zeros. On the seed the mean is 10.00, the median is 4 and 42 locations have none, so the mean overstates the typical location because a few busy locations pull it up. I would show the median and the number of empty locations to the customer and keep the mean as a secondary number.

**Source:** `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:68-76`
```sql
SELECT round(avg(n), 2)                                 AS mean_sites,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY n)   AS median_sites,
       count(*) FILTER (WHERE n = 0)                    AS locations_with_none
FROM (
  SELECT l.id, count(s.id) AS n
  FROM disaster_locations l
  LEFT JOIN site_assessments s ON s.location_id = l.id
  GROUP BY l.id
) per_location;
```

I would say that the grain is one row per location after the inner subquery, and that the join type and the count column are the two decisions that make the zeros appear.

**Q:** Why do funnel counts go wrong when you join three tables, and how does the repo avoid it?

**A:** A location joined to its assessments and then to its photos fans out, so one location with 12 assessments and 8 photos each becomes 96 rows, and counting those rows makes a funnel that grows instead of shrinking. The fix is to count distinct entities per stage, which in my funnel query (`queries/06_funnel_location_assessment_photo.sql`) means collapsing the photo side to one row per assessment with `SELECT DISTINCT site_assessment_id` before joining. On the seed, joining all three tables gives 14,530 rows for only 157 distinct locations, which shows how far the raw row count is from the truth.

**Illustrative (not from the repo):**
```sql
SELECT count(*) AS joined_rows, count(DISTINCT l.id) AS locations
FROM disaster_locations l
JOIN site_assessments s ON s.location_id = l.id
JOIN photos p ON p.site_assessment_id = s.id;
```

I would say that this shows the fan-out in one line: 14,530 rows against 157 locations, so the stage must be counted by distinct id.

### 🔴 Senior

**Q:** Write the query for "how many published events has each consumer not processed yet", and tell me what can go wrong.

**A:** I treat each consumer as one row from a `VALUES` list of subscriptions, join the published events it is eligible for, LEFT JOIN `processed_events` on both key columns, and count the rows where `pe.event_id IS NULL`. The trade-off is that a LEFT JOIN anti-join and `NOT EXISTS` give the same plan in this repo's own notes, but `NOT EXISTS` states the intent better and is NULL-safe. The failure modes are joining on `event_id` alone, which matches another consumer's row and hides the backlog, and `NOT IN (subquery)`, which returns zero rows if the subquery contains a single NULL. I put the condition inside `FILTER` rather than `WHERE`, so a healthy consumer still appears with a zero instead of disappearing. On the seed the notifier has 713 unprocessed events, photo-processor 131 and dashboard-aggregator 109, and these numbers belong to the synthetic data, which plants a notifier stall near the end. The boundary of the claim is that the subscription list is hard-coded in the query, so if a consumer's event types change in the application the query silently goes stale.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/09_outbox_backlog_consumer_lag.sql:36-41`
```sql
  FROM subscriptions s
  JOIN domain_events de ON de.event_type = s.event_type AND de.published_at IS NOT NULL
  LEFT JOIN processed_events pe ON pe.event_id = de.id AND pe.consumer_name = s.consumer_name
  CROSS JOIN as_of a
  GROUP BY s.consumer_name
)
```

**Illustrative (not from the repo):**
```sql
SELECT count(*) AS not_in_rows
FROM disaster_locations l
WHERE l.id NOT IN (SELECT s.location_id FROM site_assessments s UNION ALL SELECT NULL::uuid);

SELECT count(*) AS not_exists_rows
FROM disaster_locations l
WHERE NOT EXISTS (SELECT 1 FROM site_assessments s WHERE s.location_id = l.id);
```

I would say that I injected one NULL on purpose: `NOT IN` returns 0 rows and `NOT EXISTS` returns the correct 42. In the real table `location_id` is `NOT NULL`, so the trap is latent, not active, and I say that honestly.

**Follow-up they will ask:** How do you know your anti-join is correct?

**A:** I check it against an independent formulation, which is exactly what my Go test does. For each consumer the test recomputes the backlog with a separate `NOT EXISTS` query and asserts that the two numbers are equal, and it also asserts that `backlog_over_1h` is not larger than `backlog`, which is not larger than `eligible`. The limit of that proof is that both formulations share my reading of the subscription list, so the test catches a wrong join but not a wrong business definition.

**Source:** `GolangExercise/offline-sync-app/analytics/analytics_test.go:839-850`
```go
		} else {
			want = scalarI(t, `SELECT count(*) FROM domain_events de
			                    WHERE de.event_type = 'photo.upserted' AND de.published_at IS NOT NULL
			                      AND NOT EXISTS (SELECT 1 FROM processed_events pe WHERE pe.event_id = de.id AND pe.consumer_name = $1)`, name)
			oldest = scalarF(t, `SELECT extract(epoch FROM (SELECT max(occurred_at) FROM domain_events) - min(published_at)) / 3600
			                      FROM domain_events de
			                      WHERE de.event_type = 'photo.upserted' AND de.published_at IS NOT NULL
			                        AND NOT EXISTS (SELECT 1 FROM processed_events pe WHERE pe.event_id = de.id AND pe.consumer_name = $1)`, name)
		}
		if backlog != want {
			t.Errorf("%s: backlog = %d, independent count %d", name, backlog, want)
		}
```

## Phase 2 — Window functions (row_number vs rank vs dense_rank, frames, LAG)

### 🟢 Beginner

**Q:** What is a window function, and how is it different from GROUP BY?

**A:** A window function computes a value across a set of related rows but keeps every input row in the output, while GROUP BY collapses each group into one row. I use `PARTITION BY` to say which rows belong together and `ORDER BY` inside the window to say the order they are processed in. That is why I can show each worker's daily count next to their own previous-day count without a self-join. I cannot filter on a window function in WHERE, so I compute it in a CTE first and filter in the outer query.

**Q:** What is the difference between `row_number`, `rank` and `dense_rank`?

**A:** `row_number` gives a unique number to every row, so ties are split arbitrarily unless I add a tiebreaker. `rank` gives tied rows the same number and then skips, for example 1, 1, 3. `dense_rank` gives tied rows the same number and does not skip, for example 1, 1, 2. Which one is right is a business decision: if the customer wants exactly three badges per location I use `row_number` with a stated tiebreak, and if everyone tied for a podium place should be included I use `rank`.

### 🟡 Intermediate

**Q:** For each location, who are the top three assessors, and what happens with ties?

**A:** I count assessments per location and actor in a CTE, then compute all three ranking functions side by side over the same partition so I can show the difference. The `row_number` ordering has two explicit tiebreakers, most recent assessment and then actor id, so the answer is the same on every run. Filtering on `rn <= 3` returns at most three people per location, `rnk <= 3` can return more because tied rows at the boundary all stay, and `drnk <= 3` can return the most people because it keeps the top three distinct counts.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/02_top3_per_group_ties.sql:6-25`
```sql
WITH per_actor AS (
  SELECT location_id,
         created_by       AS actor_sub,
         count(*)         AS assessments,
         max(created_at)  AS last_assessment_at
  FROM site_assessments
  GROUP BY location_id, created_by
), ranked AS (
  SELECT location_id, actor_sub, assessments,
         row_number() OVER (PARTITION BY location_id
                            ORDER BY assessments DESC, last_assessment_at DESC, actor_sub) AS rn,
         rank()       OVER (PARTITION BY location_id ORDER BY assessments DESC)             AS rnk,
         dense_rank() OVER (PARTITION BY location_id ORDER BY assessments DESC)             AS drnk
  FROM per_actor
)
SELECT l.name AS location, r.actor_sub, r.assessments, r.rn, r.rnk, r.drnk
FROM ranked r
JOIN disaster_locations l ON l.id = r.location_id
WHERE r.drnk <= 3
ORDER BY l.name, r.rn;
```

**Illustrative (not from the repo):**
```sql
WITH per_actor AS (
  SELECT location_id, created_by AS actor_sub, count(*) AS assessments, max(created_at) AS last_at
  FROM site_assessments
  GROUP BY location_id, created_by
), ranked AS (
  SELECT row_number() OVER (PARTITION BY location_id ORDER BY assessments DESC, last_at DESC, actor_sub) AS rn,
         rank() OVER (PARTITION BY location_id ORDER BY assessments DESC) AS rnk,
         dense_rank() OVER (PARTITION BY location_id ORDER BY assessments DESC) AS drnk
  FROM per_actor
)
SELECT count(*) FILTER (WHERE rn <= 3) AS rn_rows,
       count(*) FILTER (WHERE rnk <= 3) AS rank_rows,
       count(*) FILTER (WHERE drnk <= 3) AS dense_rows
FROM ranked;
```

I would say that "top three" returned 416 rows with `row_number`, 546 with `rank` and 615 with `dense_rank` on this seed, so the function I pick changes the size of the answer by almost 50 percent.

**Q:** How do I compare each worker's volume with their previous working day?

**A:** I aggregate to one row per actor and day, then use `lag(events) OVER (PARTITION BY actor_sub ORDER BY day)` to get the previous value and subtract. The first row per actor has no previous row, so `lag` returns NULL and the delta is NULL. I use `100.0` instead of `100` so the percentage is not integer division, and `NULLIF(..., 0)` so a zero previous value does not abort the query with a division by zero.

**Illustrative (not from the repo):**
```sql
SELECT day, events,
       lag(events) OVER (ORDER BY day) AS prev_active_day,
       day - lag(day) OVER (ORDER BY day) AS days_between
FROM (
  SELECT (occurred_at AT TIME ZONE 'UTC')::date AS day, count(*) AS events
  FROM domain_events
  WHERE actor_sub = 'actor-07'
  GROUP BY 1
) d
ORDER BY day
LIMIT 6;
```

I would say that `lag` is the previous active day, not the previous calendar day: on this seed actor-07 goes from 2026-08-01 to 2026-08-03 with `days_between` equal to 2, because the weekend has no row.

### 🔴 Senior

**Q:** Explain window frames, and show a bug that comes from not writing the frame explicitly.

**A:** A frame says which rows around the current row feed the aggregate, and `ROWS` counts physical rows while `RANGE` counts values of the ORDER BY key. If I write only `ORDER BY` the default frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, so rows that tie on the ORDER BY value are peers and all of them see the same running total. My running-total query shows both versions in one result: the explicit `ROWS` frame with a unique tiebreaker, and the default frame in the last column. On sparse data `ROWS 6 PRECEDING` can reach back weeks, because idle days have no row, so for a calendar week I use `RANGE BETWEEN INTERVAL '6 days' PRECEDING` or I densify first with `generate_series`. I did not measure the cost of frames; the repo notes for the sessionization query say that one sort feeds both window nodes when `PARTITION BY` and `ORDER BY` match, which is what I would look for in EXPLAIN. The boundary of my claim is that `RANGE` with an interval offset is available from Postgres 11, which the repo notes state, and I did not test older versions.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/08_running_total_share.sql:13-25`
```sql
SELECT location,
       photos,
       round(photos::numeric / sum(photos) OVER (), 4)                                    AS share,
       sum(photos) OVER (ORDER BY photos DESC, location
                         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)                AS running_photos,
       round(sum(photos) OVER (ORDER BY photos DESC, location
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)::numeric
             / sum(photos) OVER (), 4)                                                    AS cum_share,
       round(row_number() OVER (ORDER BY photos DESC, location)::numeric
             / count(*) OVER (), 4)                                                       AS pct_of_locations,
       sum(photos) OVER (ORDER BY photos DESC)                                            AS running_photos_default_frame
FROM per_location
ORDER BY photos DESC, location;
```

**Illustrative (not from the repo):**
```sql
SELECT d, n,
       sum(n) OVER (ORDER BY d) AS default_frame,
       sum(n) OVER (ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS rows_frame
FROM (VALUES (1,5),(2,3),(2,3),(3,1)) t(d,n)
ORDER BY d;
```

I would say that the two tied rows on day 2 both show 11 under the default frame, while the explicit `ROWS` frame shows 8 and then 11, and that is the whole bug in four rows.

**Follow-up they will ask:** Can you count distinct values in a running window, for example distinct workers ever seen by day?

**A:** No, Postgres rejects `count(DISTINCT x) OVER (...)` with the error "DISTINCT is not implemented for window functions", and I confirmed that error in the container. The workaround I use is to compute each worker's first-seen day, count how many workers first appeared on each day, and then take a running `sum` of that count. The trade-off is one extra aggregation step, and days with no new worker have no row, so I join to a `generate_series` if the customer needs a continuous line.

## Phase 3 — Percentiles and time-series bucketing (percentile_cont, date_trunc, generate_series)

### 🟢 Beginner

**Q:** Why do you report the median and the 99th percentile instead of the average for latency?

**A:** Latency is long-tailed, so a few very slow requests pull the mean far away from what a typical request feels like and hide how bad the worst cases are. The median tells me the typical experience and the 99th percentile tells me what the slowest one percent of users see. In my sync-lag data the clients are offline-first and queue writes, so the median is seconds while the tail is hours. A single average would describe neither group.

**Q:** What is the difference between `percentile_cont` and `percentile_disc`?

**A:** `percentile_cont` interpolates between the two nearest values and can return a number that is not in the data, and `percentile_disc` returns an actual observed value. For the four values 1, 2, 3 and 100 the continuous median is 2.5 and the discrete median is 2. I use the continuous one for durations and the discrete one when the answer must be a real observed value, such as an identifier or a category.

### 🟡 Intermediate

**Q:** How do you get the median, p90, p99 and the p99 of the last 14 days for each metric in one pass?

**A:** I stack the three lag measures into one `samples` CTE with `UNION ALL`, so each row has a metric name, a segment and a number of seconds. Then I group by metric and segment and call `percentile_cont(...) WITHIN GROUP (ORDER BY secs)` for each percentile. The `FILTER (WHERE ...)` clause goes after `WITHIN GROUP` and restricts which rows feed that one aggregate, which is how I get the all-time p99 and the last-14-days p99 side by side. The 14-day cutoff is computed on UTC wall-clock timestamps, which I come back to in phase 5.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/04_latency_percentiles.sql:23-33`
```sql
SELECT metric,
       segment,
       count(*)                                                                    AS n,
       round((percentile_cont(0.50) WITHIN GROUP (ORDER BY secs))::numeric, 3)     AS p50_s,
       round((percentile_cont(0.90) WITHIN GROUP (ORDER BY secs))::numeric, 3)     AS p90_s,
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY secs))::numeric, 3)     AS p99_s,
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY secs)
                FILTER (WHERE at AT TIME ZONE 'UTC' >= (SELECT ts FROM as_of) - interval '14 days'))::numeric, 3) AS p99_s_last_14d
FROM samples
GROUP BY metric, segment
ORDER BY metric, segment;
```

**Illustrative (not from the repo):**
```sql
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY v) AS cont_median,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY v) AS disc_median,
       avg(v) AS mean
FROM (VALUES (1),(2),(3),(100)) t(v);

SELECT round(avg(extract(epoch FROM occurred_at - (payload ->> 'updatedAt')::timestamptz))::numeric / 3600, 2) AS mean_h,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM occurred_at - (payload ->> 'updatedAt')::timestamptz)))::numeric / 3600, 3) AS p50_h,
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM occurred_at - (payload ->> 'updatedAt')::timestamptz)))::numeric / 3600, 2) AS p99_h
FROM domain_events;
```

I would say that the toy data gives 2.5, 2 and 26.5, and that the real sync lag on the seed has a mean of about 0.51 hours, a median of about 0.001 hours and a p99 of about 8.74 hours, so the three numbers describe three different things.

**Q:** How do I show quiet time buckets, such as an hour with zero events?

**A:** Grouping by `date_trunc` only returns buckets that have rows, so an outage is invisible, because no rows is not the same as zero. I generate every bucket with `generate_series` and LEFT JOIN the events onto it with a half-open range, `>= start AND < start + 1 hour`, which also lets a btree on the timestamp be used. I use `count(de.id)` and not `count(*)`, because `count(*)` would count the empty bucket as one. I generate the series on `timestamp` without time zone, produced with `AT TIME ZONE 'UTC'`, so no hour is skipped or repeated by daylight saving.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/13_gaps_silent_hours.sql:10-20`
```sql
), hours AS (
  SELECT g.h
  FROM bounds b
  CROSS JOIN LATERAL generate_series(b.first_hour, b.last_hour, interval '1 hour') AS g(h)
), hourly AS (
  SELECT h.h AS hour_start, count(de.id) AS events
  FROM hours h
  LEFT JOIN domain_events de
         ON de.occurred_at >= h.h AT TIME ZONE 'UTC'
        AND de.occurred_at <  (h.h + interval '1 hour') AT TIME ZONE 'UTC'
  GROUP BY h.h
```

**Illustrative (not from the repo):**
```sql
SELECT g.h AS hour_utc, count(de.id) AS events
FROM generate_series(timestamp '2026-08-13 08:00', timestamp '2026-08-13 17:00', interval '1 hour') AS g(h)
LEFT JOIN domain_events de
       ON de.occurred_at >= g.h AT TIME ZONE 'UTC'
      AND de.occurred_at <  (g.h + interval '1 hour') AT TIME ZONE 'UTC'
GROUP BY g.h
ORDER BY g.h;
```

I would say that this prints six rows of zero for 10:00 to 15:59 UTC on 2026-08-13, which is the outage the seed plants, and a plain `GROUP BY date_trunc('hour', ...)` over the same window returns only four rows and shows no outage at all.

### 🔴 Senior

**Q:** Can I pre-aggregate p99 per actor or per day and combine them later?

**A:** No, percentiles do not compose: the average of per-group p99 values is not the p99 of the pooled data. On the seed, the average of the 25 per-actor p99 values of sync lag is about 5.47 hours, while the pooled p99 is about 8.74 hours, a gap of more than 3 hours. If I need to pre-aggregate I would store a histogram or a t-digest, or recompute from raw rows. Exact percentiles sort each group, which is O(n log n) in time and memory, and that is fine at 50,680 rows, but I did not measure it at larger sizes and I would move to approximate quantiles in a warehouse at hundreds of millions of rows. The boundary of the claim is the synthetic data: the exact gap depends on how skewed the seed is, but the direction of the error does not.

**Illustrative (not from the repo):**
```sql
WITH s AS (
  SELECT actor_sub, extract(epoch FROM occurred_at - (payload ->> 'updatedAt')::timestamptz) AS secs
  FROM domain_events
), per AS (
  SELECT actor_sub, percentile_cont(0.99) WITHIN GROUP (ORDER BY secs) AS p99
  FROM s
  GROUP BY actor_sub
)
SELECT round((SELECT avg(p99) FROM per)::numeric / 3600, 2) AS avg_of_actor_p99_h,
       round((SELECT percentile_cont(0.99) WITHIN GROUP (ORDER BY secs) FROM s)::numeric / 3600, 2) AS pooled_p99_h;
```

I would say that this one result is my proof that you cannot average percentiles, and that I measured it on synthetic data.

**Follow-up they will ask:** Which time zone does a weekly bucket use, and what goes wrong if you ignore the question?

**A:** `date_trunc('week', timestamptz)` uses the session time zone, so the same instant can fall into different weeks for different sessions. I apply `AT TIME ZONE 'UTC'` first and truncate the resulting `timestamp`, so the bucket is a Monday in UTC no matter how the session is configured. The related trap is that `generate_series(date, date, interval)` resolves to the `timestamptz` overload and follows the session time zone, so I cast the bounds to `timestamp`. I verified both in the container, and my repo test runs every query under UTC and Pacific/Auckland sessions to keep it that way. The cost is that "week" now means UTC week, so for a customer in another zone I would state the definition on the chart.

**Illustrative (not from the repo):**
```sql
SELECT date_trunc('week', timestamptz '2026-07-05 23:30+00' AT TIME ZONE 'UTC')::date AS utc_week;

SET TIME ZONE 'Pacific/Auckland';

SELECT date_trunc('week', timestamptz '2026-07-05 23:30+00') AS auckland_session_week;

SELECT pg_typeof(g) FROM generate_series(date '2026-01-01', date '2026-01-03', interval '1 day') g LIMIT 1;
```

I would say that the same instant lands in the week of 2026-06-29 under UTC and in the week of 2026-07-06 in an Auckland session, and that the `date` series comes back as `timestamp with time zone`.

**Source:** `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:251-256`
```sql
SELECT date_trunc('week', occurred_at AT TIME ZONE 'UTC')::date AS week,
       round((percentile_cont(0.99) WITHIN GROUP (
                ORDER BY extract(epoch FROM occurred_at - (payload ->> 'updatedAt')::timestamptz)) / 3600)::numeric, 2) AS p99_sync_lag_hours
FROM domain_events
GROUP BY 1
ORDER BY 1;
```

I would say that this is my weekly p99 for the dashboard: it ranges from about 5.77 to 11.03 hours across the 14 weeks on the seed, the first and last weeks are partial because the data runs from Wednesday 2026-07-01 to Monday 2026-09-28, and I do not read a trend into it.

## Phase 4 — Cohorts, funnels and sessionization (gaps and islands)

### 🟢 Beginner

**Q:** What is a cohort, and what is retention?

**A:** A cohort is a group of users who started in the same period, for example the week of their first event. Retention is the share of that cohort that is still active some number of periods later. I use it to answer whether newer groups stick better than older ones. I always say what counts as "active" and what the denominator is, because a cohort of three people moves a percentage by 33 points when one person leaves.

**Q:** What is a funnel, and what is the most common mistake in one?

**A:** A funnel counts how many entities reach each stage, for example location opened, assessment created, photo taken, and the conversion between stages tells me where I lose them. The most common mistake is counting joined rows instead of distinct entities, which makes a later stage look bigger than an earlier one. The second is mixing grains: on my seed 200 locations lead to 158 with an assessment and 157 with a photo, but only 1,757 of 2,000 assessments, about 88 percent, have a photo. I say which grain I report.

### 🟡 Intermediate

**Q:** How do you split an event stream into sessions with a 30-minute inactivity gap?

**A:** I use gaps and islands in three steps. First I use `lag(occurred_at)` over each actor to get the previous event time, then I flag a row as a session start when there is no previous row or the gap is greater than 30 minutes, and then a running sum of the flags gives the session number. The order includes the unique id so that the order is total and rows with equal timestamps are not peers. The first event has a NULL previous time, so I handle it with an explicit `IS NULL` branch, because a NULL comparison would otherwise fall into the ELSE branch and the numbering would start at zero.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/05_sessionization_islands.sql:6-25`
```sql
WITH ordered AS (
  SELECT id, actor_sub, occurred_at,
         lag(occurred_at) OVER (PARTITION BY actor_sub ORDER BY occurred_at, id) AS prev_at
  FROM domain_events
), flagged AS (
  SELECT *,
         CASE WHEN prev_at IS NULL OR occurred_at - prev_at > interval '30 minutes' THEN 1 ELSE 0 END AS starts_session
  FROM ordered
), numbered AS (
  SELECT *,
         sum(starts_session) OVER (PARTITION BY actor_sub ORDER BY occurred_at, id
                                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_no
  FROM flagged
), sessions AS (
  SELECT actor_sub, session_no,
         count(*)                           AS events,
         max(occurred_at) - min(occurred_at) AS duration
  FROM numbered
  GROUP BY actor_sub, session_no
)
```

**Illustrative (not from the repo):**
```sql
SELECT ts, ts - lag(ts) OVER (ORDER BY ts) > interval '30 minutes' AS new_session
FROM (VALUES (timestamptz '2026-07-01 08:00+00'),
             (timestamptz '2026-07-01 08:30+00'),
             (timestamptz '2026-07-01 09:00:01+00')) t(ts);
```

I would say that the first row is NULL, a gap of exactly 30:00 stays in the session because I use `>` and not `>=`, and a gap of 30:01 or more starts a new one, so I always state the boundary.

**Q:** How do you compute weekly cohort retention including the cells where nobody came back?

**A:** I take each actor's first active week as the cohort, build a grid of every cohort and every week offset with `generate_series`, and LEFT JOIN the activity onto the grid. The grid is what turns a dead cohort into a row with 0 percent instead of a missing row that looks like missing data. I exclude the last partial week with a `last_complete` CTE, because counting it would make every cohort look like it churned in a week that has not finished. The weeks are truncated after `AT TIME ZONE 'UTC'`, and `date - date` is an integer number of days, so dividing by 7 is integer division on purpose.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/07_weekly_retention_cohort.sql:10-36`
```sql
), last_complete AS (
  SELECT (date_trunc('week', max(occurred_at AT TIME ZONE 'UTC')) - interval '7 days')::date AS week
  FROM domain_events
), cohort AS (
  SELECT actor_sub, min(week) AS cohort_week
  FROM activity
  GROUP BY actor_sub
), cohort_size AS (
  SELECT cohort_week, count(*) AS size
  FROM cohort
  GROUP BY cohort_week
), grid AS (
  SELECT cs.cohort_week, cs.size, n.n
  FROM cohort_size cs
  CROSS JOIN last_complete lc
  CROSS JOIN LATERAL generate_series(0, (lc.week - cs.cohort_week) / 7) n(n)
)
SELECT g.cohort_week,
       g.size                                        AS cohort_size,
       g.n                                           AS weeks_since_start,
       count(a.actor_sub)                            AS active_actors,
       round(count(a.actor_sub)::numeric / g.size, 4) AS retention
FROM grid g
JOIN cohort c       ON c.cohort_week = g.cohort_week
LEFT JOIN activity a ON a.actor_sub = c.actor_sub AND a.week = g.cohort_week + g.n * 7
GROUP BY g.cohort_week, g.size, g.n
ORDER BY g.cohort_week, g.n;
```

I would say that this is classic retention, active exactly n weeks later, and not rolling retention, and that with only 25 actors the cohorts have between 1 and 8 people, so one person moves a cell by 12 to 100 points.

### 🔴 Senior

**Q:** How sensitive is the session answer to the threshold, and what clock should the sessions use?

**A:** Very sensitive, so the threshold is a product decision and not a technical one. On the seed the same query gives about 6,594 sessions at 15 minutes, 4,759 at 30 minutes and 2,350 at 60 minutes, and I measured that in the container. The second issue is the clock: my sessions use `occurred_at`, which is server time, so an offline worker's queued day arrives as one sync burst and collapses into one session. For field-work sessions I would use the device timestamp from the payload, at the cost of device clock skew. The boundary of the claim is that these counts come from synthetic data with planted offline lag and a planted outage, so they show the sensitivity but are not a benchmark of anything real.

**Illustrative (not from the repo):**
```sql
SELECT m AS threshold_minutes, sum(starts) AS sessions
FROM (VALUES (15), (30), (60)) t(m)
CROSS JOIN LATERAL (
  SELECT CASE WHEN prev_at IS NULL OR occurred_at - prev_at > t.m * interval '1 minute' THEN 1 ELSE 0 END AS starts
  FROM (
    SELECT occurred_at, lag(occurred_at) OVER (PARTITION BY actor_sub ORDER BY occurred_at, id) AS prev_at
    FROM domain_events
  ) o
) x
GROUP BY m
ORDER BY m;
```

I would say that it counts session starts per threshold, and that I treat the number of sessions as a function of a parameter and never as a fact.

**Follow-up they will ask:** Show me the classic island trick for consecutive days, and why do you take DISTINCT first?

**A:** For consecutive days, `day - row_number()` is constant inside a streak, because both advance by one per row and the difference changes only when a day is skipped. I take one row per actor and day first, because `row_number` over raw events advances several times per day and breaks the arithmetic. I then group by the constant to get the start, end and length of each streak and pick the longest with `row_number` ordered by length descending and then start, so a tie is broken deterministically. The streak is a calendar streak, so a weekend with no events ends it, and a working-day streak would need a calendar table. The same trick on hours finds the silent runs in `queries/13_gaps_silent_hours.sql`: I number the empty working hours, subtract that many hours, and group by the constant.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/14_activity_streaks.sql:9-19`
```sql
), numbered AS (
  SELECT actor_sub, day,
         day - (row_number() OVER (PARTITION BY actor_sub ORDER BY day))::int AS island
  FROM active_days
), streaks AS (
  SELECT actor_sub, island,
         min(day)  AS streak_start,
         max(day)  AS streak_end,
         count(*)  AS streak_days
  FROM numbered
  GROUP BY actor_sub, island
```

**Illustrative (not from the repo):**
```sql
SELECT d, d - (row_number() OVER (ORDER BY d))::int AS island
FROM (VALUES (date '2026-07-01'), (date '2026-07-02'), (date '2026-07-03'),
             (date '2026-07-06'), (date '2026-07-07')) t(d);
```

I would say that the first three days share the island value 2026-06-30 and the last two share 2026-07-02, so grouping by that value yields streaks of 3 and 2 days. The seeded 6-hour outage on 2026-08-13 is found this way as one island of 6 silent hours, and the limitation is that restricting to working hours before numbering splits a silence that crosses 18:59 to 07:00 into two runs.

## Phase 5 — Data quality (dedupe, time zones and DST, determinism)

### 🟢 Beginner

**Q:** How do you remove duplicates in SQL?

**A:** First I decide what makes two rows the same logical record, which is the business key, and I do not assume the primary key is that key. In my event log every row has a fresh uuid even when it is a duplicate of another write, so the logical key is the aggregate id plus the record's `updatedAt` version. Then I number the rows inside each key with `row_number()` and keep the first or the latest. I do not delete from an audit log, I use a view or a `CREATE TABLE AS` of the kept rows.

**Q:** Why does the time zone change my "events per day" number?

**A:** A timestamp with time zone is one instant, but the calendar day it belongs to depends on the zone you look at it in. On my seed the same calendar day, 2026-07-23, holds 1,443 events by UTC date, 1,389 by Asia/Kolkata and 889 by Pacific/Auckland, which I measured in the container and which `QUESTIONS.md` question 10 records. So I pick the zone on purpose, write it into the query with `AT TIME ZONE`, and say it next to the chart.

### 🟡 Intermediate

**Q:** How many distinct writes did the field staff really make compared with the number of outbox rows?

**A:** I define a logical write as the pair of aggregate id and `payload.updatedAt`, number the copies with `row_number()` ordered by latest `occurred_at` and then `id`, and count `rn = 1` as distinct and `rn > 1` as duplicates, all in one pass with `FILTER`. Keeping the latest copy gives me the freshest publish state, while keeping the first would preserve the original arrival time, so I say which I chose and why. On the seed there are 50,680 raw rows, 49,001 distinct writes and 1,679 duplicate rows, about 3.3 percent, and the seed injects roughly 3 percent on purpose. The consumer idempotency table keys on event id, so duplicates with different ids are processed again downstream, which is how a customer dashboard can over-count.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/11_dedupe_latest.sql:6-21`
```sql
WITH ranked AS (
  SELECT id, event_type, occurred_at,
         row_number() OVER (PARTITION BY aggregate_id, payload ->> 'updatedAt'
                            ORDER BY occurred_at DESC, id DESC) AS rn,
         count(*)     OVER (PARTITION BY aggregate_id, payload ->> 'updatedAt')              AS copies
  FROM domain_events
)
SELECT event_type,
       count(*)                                        AS raw_rows,
       count(*) FILTER (WHERE rn = 1)                  AS distinct_writes,
       count(*) FILTER (WHERE rn > 1)                  AS duplicate_rows,
       round(count(*) FILTER (WHERE rn > 1)::numeric / count(*), 4) AS duplicate_rate,
       max(copies)                                     AS max_copies_of_one_write
FROM ranked
GROUP BY event_type
ORDER BY event_type;
```

**Illustrative (not from the repo):**
```sql
SELECT count(*) AS events,
       count(DISTINCT (aggregate_id, payload ->> 'updatedAt')) AS distinct_writes
FROM domain_events;
```

I would say that this independent `count(DISTINCT ...)` returns 50,680 and 49,001, which is the oracle my Go test uses to check the window-function version.

**Q:** What is the daylight-saving bug with `interval '14 days'` on a `timestamptz`, and how is it handled in your code?

**A:** Subtracting `interval '14 days'` from a `timestamptz` is calendar arithmetic in the session time zone, so across a daylight-saving change it is not 336 hours and the cutoff moves by an hour. The repo's comment in the percentile query records that a test running the query under two session zones caught this; I could not find git history for the original failing run, so I rely on the comment and on the reproduction below. The fix in the code is to convert to UTC wall-clock `timestamp` first with `AT TIME ZONE 'UTC'` and subtract the interval there, where a day is always 24 hours. In my reproduction the cutoff in an Auckland session is one hour later than in UTC, and on this seed the row count in the window happened to be the same, 6,227 rows, because no event fell in that hour. A boundary bug can hide until an event lands in the shifted hour.

**Source:** `GolangExercise/offline-sync-app/analytics/queries/04_latency_percentiles.sql:29-30`
```sql
       round((percentile_cont(0.99) WITHIN GROUP (ORDER BY secs)
                FILTER (WHERE at AT TIME ZONE 'UTC' >= (SELECT ts FROM as_of) - interval '14 days'))::numeric, 3) AS p99_s_last_14d
```

**Illustrative (not from the repo):**
```sql
SELECT current_setting('TimeZone') AS session_zone,
       (SELECT max(occurred_at) FROM domain_events) - interval '14 days' AS cutoff_calendar,
       (SELECT max(occurred_at) FROM domain_events) - interval '336 hours' AS cutoff_336h,
       (SELECT count(*) FROM domain_events
        WHERE occurred_at >= (SELECT max(occurred_at) FROM domain_events) - interval '14 days') AS rows_in_window;

SET TIME ZONE 'Pacific/Auckland';

SELECT current_setting('TimeZone') AS session_zone,
       (SELECT max(occurred_at) FROM domain_events) - interval '14 days' AS cutoff_calendar,
       (SELECT max(occurred_at) FROM domain_events) - interval '336 hours' AS cutoff_336h,
       (SELECT count(*) FROM domain_events
        WHERE occurred_at >= (SELECT max(occurred_at) FROM domain_events) - interval '14 days') AS rows_in_window;
```

I would say that in the UTC session both cutoffs equal 2026-09-14 19:15:57 UTC, and in the Auckland session the calendar cutoff is 2026-09-15 08:15:57+12, which is 20:15:57 UTC, one hour later than the 336-hour cutoff. The seed ends on 2026-09-28, and I believe New Zealand daylight time started on 2026-09-27, so this window crosses it; verify the exact date in the tz database if it matters.

### 🔴 Senior

**Q:** How do you make an analytics result reproducible, and how do you prove it?

**A:** I remove every source of hidden variation and then test for it. The seed takes its randomness from `md5` of a key and never from `random()`, so it does not depend on row order or plan. Every ranking and window has a total order with an id tiebreaker, the "as of" time is the data's own `max(occurred_at)` and not `now()`, and day and week buckets go through `AT TIME ZONE 'UTC'`. To prove it, the Go test runs every query under UTC and Pacific/Auckland sessions and asserts that the rendered results are identical, and it reseeds and compares fingerprints of each table before and after. The trade-off is that using the data's own maximum makes a query reproducible but means that in production I must substitute `now()` deliberately and say so. What I have not done in this session is run the Go tests, because they reseed the database, so I am citing their code and not a fresh pass.

**Source:** `GolangExercise/offline-sync-app/analytics/seed/seed.sql:13-14`
```sql
CREATE OR REPLACE FUNCTION pg_temp.u(k text) RETURNS float8 LANGUAGE sql IMMUTABLE AS
$$ SELECT (('x' || substr(md5(k), 1, 8))::bit(32)::bigint)::float8 / 4294967296.0 $$;
```

**Source:** `GolangExercise/offline-sync-app/analytics/analytics_test.go:287-314`
```go
func TestQueryResultsDoNotDependOnSessionTimeZone(t *testing.T) {
	ctx := context.Background()
	render := func(zone, sql string) string {
		tx, err := pool.Begin(ctx)
		if err != nil {
			t.Fatal(err)
		}
		defer tx.Rollback(ctx)
		if _, err := tx.Exec(ctx, "SET LOCAL TIME ZONE '"+zone+"'"); err != nil {
			t.Fatal(err)
		}
		rs, err := query(ctx, tx, sql)
		if err != nil {
			t.Fatalf("%s: %v", zone, err)
		}
		return renderRowset(rs)
	}
	for _, f := range queryFiles(t) {
		sql := readFile(t, f)
		t.Run(queryName(f), func(t *testing.T) {
			utc := render("UTC", sql)
			auckland := render("Pacific/Auckland", sql)
			if utc != auckland {
				t.Fatal("result differs between UTC and Pacific/Auckland session time zones")
			}
		})
	}
}
```

I would say that the test compares UTC with Auckland because Auckland has a large offset from UTC and, as I believe, a daylight-saving change near the end of the seed window, so it is a zone likely to expose a session-dependent expression.

**Follow-up they will ask:** Is a query that passes your invariants correct?

**A:** No, it is consistent with the checks I wrote, and the checks are only as good as my independent oracles. For the dedupe query the test recomputes the distinct count with `count(DISTINCT ...)` and asserts that raw equals distinct plus duplicates, which would catch a broken partition or filter. It would not catch a wrong business key, for example if `updatedAt` were not the right version marker, and it cannot detect an upstream bug I have not modelled. I would say that out loud and add a reconciliation against a source of truth when one exists.

## Phase 6 — Performance (EXPLAIN ANALYZE, BUFFERS, indexes)

### 🟢 Beginner

**Q:** What does an index do, and what does EXPLAIN show?

**A:** An index is a sorted structure that lets the database jump to matching rows instead of reading the whole table. `EXPLAIN` shows the plan the planner chose, and `EXPLAIN ANALYZE` also runs the query and shows actual times and row counts. Adding `BUFFERS` shows how many 8 kB pages were touched, which is the number I trust more than the timing, because timing moves with caches and machines. I read the plan for a Seq Scan on a big table with a selective filter, which usually means a missing index.

**Q:** Does every slow-looking query need an index?

**A:** No. An analytical query that must read every row, such as a daily count over the whole event table, is a full scan whichever index I add. My 14 analytical queries need no index for that reason, and only the three lookups a customer-facing screen would run were worth indexing in my study. Every extra index also slows writes, so I add one only when a selective, repeated lookup justifies it.

### 🟡 Intermediate

**Q:** Walk me through the before and after of an index in your EXPLAIN study.

**A:** The query, `explain/01_aggregate_history.sql`, is the audit trail of one aggregate, a lookup on `aggregate_id` ordered by `occurred_at`. Before the index the only options were the primary key on `id` and a partial index on unpublished rows, so the planner read the whole table with a Seq Scan, 6.11 ms and 3,063 buffers, to return 13 rows. After I created a composite index on `(aggregate_id, occurred_at)` it used a Bitmap Index Scan, 0.105 ms and 10 buffers, about 58 times faster. These numbers are from one local Postgres 16.15 container on one Apple Silicon laptop with synthetic data, fully in `shared_buffers`, median of six runs, so they are order-of-magnitude and not a benchmark.

**Source:** `GolangExercise/offline-sync-app/analytics/indexes.sql:1-5`
```sql
CREATE INDEX IF NOT EXISTS domain_events_aggregate_idx ON domain_events (aggregate_id, occurred_at);
CREATE INDEX IF NOT EXISTS domain_events_actor_time_idx ON domain_events (actor_sub, occurred_at);
CREATE INDEX IF NOT EXISTS processed_events_consumer_time_idx ON processed_events (consumer_name, processed_at);
ANALYZE domain_events;
ANALYZE processed_events;
```

**Source:** `GolangExercise/offline-sync-app/analytics/EXPLAIN.md:7-11`
```text
| # | Query | Before | After | Buffers before / after | Speed-up |
|---|-------|--------|-------|------------------------|----------|
| 1 | audit trail of one aggregate (`aggregate_id = ...`, 13 rows) | 6.11 ms, Seq Scan | 0.105 ms, Bitmap Index Scan | 3,063 / 10 | about 58x |
| 2 | one actor's recent activity (`actor_sub = ... AND occurred_at >= ...`, 450 rows) | 8.54 ms, Seq Scan | 0.46 ms, Bitmap Index Scan | 3,063 / 93 | about 19x |
| 3 | one consumer's recent processing (`consumer_name = ... AND processed_at >= ...`, 1,051 rows) | 4.32 ms, Seq Scan | 0.22 ms, Index Only Scan | 1,081 / 9 | about 19x |
```

I would say that the buffer count is the clearest column: 3,063 pages down to 10, with the caveat that the timing columns are local, one machine and synthetic.

**Q:** Why did the primary key not help the consumer query, and what made the third plan an Index Only Scan?

**A:** `processed_events` has the primary key `(event_id, consumer_name)`, and a btree can only seek on its leading column, so a filter on `consumer_name` alone could not use it and the planner chose a Seq Scan. The new index on `(consumer_name, processed_at)` contains both predicates, and because the query needs only `count(*)` and `max(processed_at)` it can be answered from the index alone, which is an Index Only Scan at 0.22 ms against 4.32 ms. The repo notes that Postgres 16 has no skip scan and that it arrived in a later release; I am not certain of that, so verify it in the current docs before repeating it. `Heap Fetches: 0` also depends on the visibility map being current, which I did not control.

**Source:** `GolangExercise/offline-sync-app/migrations/000002_add_domain_events.up.sql:23-28`
```sql
CREATE TABLE processed_events (
    event_id      UUID NOT NULL,
    consumer_name TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer_name)
);
```

I would say that the equality column goes first and the range column second, and that the column order of a composite index is the whole design.

### 🔴 Senior

**Q:** The planner chose a bitmap scan and a Sort over a plain index scan that avoids the Sort. Was that wrong?

**A:** It was right here, and the measurements show why. With `enable_bitmapscan` set to off, a single run each, the plain Index Scan removed the Sort because `occurred_at` is the second index column, but it was slower: 0.25 ms against 0.075 ms for the aggregate lookup and 1.22 ms against 0.42 ms for the actor lookup, with 374 buffers against 93 for the actor lookup. One actor's rows are scattered across the heap, so a plain index scan revisits pages while a bitmap scan visits each page once. The failure mode is trusting the "no Sort" plan by instinct, and the boundary of the claim is that these are single runs on a warm cache, so I would not quote the ratios as constants. The cost I did not measure is the write side: `domain_events` is the transactional outbox written on every sync, and two more indexes mean three btrees maintained per insert instead of one.

I would say that my `TestIndexesChangeThePlans` test pins the plan shape and not the timing: before the indexes every plan must have a Seq Scan and no index node, and after them an index plan and no Seq Scan, so the study cannot silently drift.

**Follow-up they will ask:** Where does an index fail to help, and how do you see it?

**A:** An index does not help when the predicate wraps the indexed column in a function, because the function result is not what the btree stores. In `EXPLAIN` I look at whether a condition appears under `Index Cond` or under `Filter` plus `Rows Removed by Filter`. In the container, with the study indexes present, a query for one actor and one day wrapped in `date_trunc` put only `actor_sub` in `Index Cond`, filtered out 1,657 rows, touched 14 buffers and took about 0.5 ms (0.479 and 0.516 ms in two runs), while the half-open range version put all three predicates in `Index Cond`, touched 4 buffers and took between 0.014 and 0.058 ms in the same two runs. Those are warm single-machine runs, so I take the buffers and the `Index Cond` versus `Filter` split seriously and the milliseconds loosely. The partial index on unpublished rows is the other design I use: the relay's poll only looks at `published_at IS NULL`, so a small partial index serves it.

**Illustrative (not from the repo):**
```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FROM domain_events
WHERE actor_sub = 'actor-07'
  AND date_trunc('day', occurred_at, 'UTC') = timestamptz '2026-08-13 00:00+00';

EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FROM domain_events
WHERE actor_sub = 'actor-07'
  AND occurred_at >= timestamptz '2026-08-13 00:00+00'
  AND occurred_at <  timestamptz '2026-08-14 00:00+00';
```

I would say that I read the plan for `Index Cond` versus `Filter`, and that the half-open range is why my bucketed queries join on `>= start AND < start + interval` and never on `date_trunc(col) = bucket`.

**Source:** `GolangExercise/offline-sync-app/migrations/000002_add_domain_events.up.sql:17-18`
```sql
-- Partial index: the relay's poll query only ever looks at unpublished rows.
CREATE INDEX domain_events_unpublished_idx ON domain_events (occurred_at) WHERE published_at IS NULL;
```

## Phase 7 — From a query to a dashboard that informs one decision

### 🟢 Beginner

**Q:** What makes a dashboard useful to a customer?

**A:** A useful dashboard exists to inform one decision, and every chart on it should change what the customer does next. I start by asking what decision the customer needs to make this week and what they would do differently for each possible answer. Then I choose the fewest metrics that rank the options. Extra charts make the customer re-derive the ranking on their own.

**Q:** Why do you alert on age and not only on volume?

**A:** Volume can look healthy while events are being lost. In my seed the stuck outbox rows are well under one percent of the events, so a throughput chart looks normal while those rows are never delivered. The age of the oldest stuck row grows every day and cannot hide in a total. So I alert on the oldest age and on the trend of the tail, and I show the count as a size signal.

### 🟡 Intermediate

**Q:** What is the one decision in your dashboard, and what is the first metric?

**A:** The decision is which hop of the pipeline an engineer should work on this week: the offline client sync path, the outbox relay or a consumer. Each metric points at exactly one hop, so together they rank the options. The relay metric is a single number, the count of outbox rows that are still unpublished after more than an hour, plus the age of the oldest. I measure age against the data's own latest event time so the result is reproducible, and in production I would use `now()` and say that I substituted it.

**Source:** `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:264-269`
```sql
SELECT count(*)                                                                    AS stuck_outbox_rows,
       round((extract(epoch FROM max(a.ts - de.occurred_at)) / 3600)::numeric, 1)  AS oldest_hours
FROM domain_events de
CROSS JOIN (SELECT max(occurred_at) AS ts FROM domain_events) a
WHERE de.published_at IS NULL
  AND a.ts - de.occurred_at > interval '1 hour';
```

**Illustrative (not from the repo):**
```sql
SELECT count(*) FILTER (WHERE published_at IS NULL) AS unpublished,
       round(100.0 * count(*) FILTER (WHERE published_at IS NULL) / count(*), 2) AS pct_of_events
FROM domain_events;
```

I would say that on the seed 228 rows are unpublished, 227 of them for more than an hour as the Source above counts, which is about 0.45 percent of the 50,680 events, and that this is a planted property of the synthetic data.

### 🔴 Senior

**Q:** Defend the three-metric dashboard and the ranking it produces.

**A:** The three metrics are the weekly p99 of client sync lag, the stuck outbox rows with the age of the oldest, and the unprocessed events per consumer, one per hop. On the seed the p99 sync lag sits between about 5.77 and 11.03 hours with no upward trend, and because the clients are offline-first that lag is structural, so the verdict is to leave that hop alone. The relay shows 227 rows stuck over an hour, the oldest about 2,140 hours, which is silent data loss because those events never reach any consumer. The notifier shows 713 unprocessed events, photo-processor 131 and dashboard-aggregator 109, and the notifier number is driven by a stall in the final hours of the data. My ranking is relay first because it is silent loss, notifier second because it is live and fixable by restart, and sync path last. The trade-off is that I chose a ranking by severity and not by count, since the notifier count is larger. The boundary of the claim is that every count is planted by the seed, so this shows the method and not a finding about a real system.

**Source:** `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:277-284`
```sql
SELECT pe_c.consumer_name,
       count(*) FILTER (WHERE pe.event_id IS NULL AND a.ts - de.published_at > interval '1 hour') AS unprocessed_over_1h
FROM (VALUES ('photo-processor'), ('dashboard-aggregator'), ('notifier')) pe_c(consumer_name)
CROSS JOIN (SELECT max(occurred_at) AS ts FROM domain_events) a
JOIN domain_events de ON de.event_type = 'photo.upserted' AND de.published_at IS NOT NULL
LEFT JOIN processed_events pe ON pe.event_id = de.id AND pe.consumer_name = pe_c.consumer_name
GROUP BY pe_c.consumer_name
ORDER BY unprocessed_over_1h DESC;
```

I would say that a customer cannot get the ranking from any one chart, and that the ranking itself is the deliverable.

**Follow-up they will ask:** Did you build this dashboard? What would you do before putting it in front of a customer?

**A:** In this repo the dashboard is a documented design backed by three tested queries, not a deployed BI tool, and I would not claim otherwise. Before a customer sees it I would agree the definitions in writing: what "stuck" means, the one-hour threshold, whether duplicates are collapsed on the business key, and which time zone the weekly bucket uses. I would replace the data's `max(occurred_at)` with `now()` and add a freshness stamp, and I would check the three queries against a source of truth, because a dashboard that is confidently wrong is worse than none. I would also reconsider the index cost from phase 6, serving these reads from a replica or a warehouse if the outbox table is hot. I have not tested that setup, so that part is a design intent and not a measured result.

## Code reference index

| path:lines | what it shows |
|---|---|
| `GolangExercise/offline-sync-app/analytics/queries/09_outbox_backlog_consumer_lag.sql:36-41` | Consumer anti-join on both key columns |
| `GolangExercise/offline-sync-app/analytics/queries/02_top3_per_group_ties.sql:6-25` | `row_number`, `rank` and `dense_rank` side by side |
| `GolangExercise/offline-sync-app/analytics/queries/08_running_total_share.sql:13-25` | Share of total, running total and the default-frame trap |
| `GolangExercise/offline-sync-app/analytics/queries/04_latency_percentiles.sql:23-33` | `percentile_cont` with `FILTER` for all-time and last 14 days |
| `GolangExercise/offline-sync-app/analytics/queries/13_gaps_silent_hours.sql:10-20` | `generate_series` densifying with a half-open range join |
| `GolangExercise/offline-sync-app/analytics/queries/05_sessionization_islands.sql:6-25` | Sessionization: lag, flag, running sum |
| `GolangExercise/offline-sync-app/analytics/queries/07_weekly_retention_cohort.sql:10-36` | Cohort retention triangle with a `generate_series` grid |
| `GolangExercise/offline-sync-app/analytics/queries/14_activity_streaks.sql:9-19` | Date minus `row_number` island trick |
| `GolangExercise/offline-sync-app/analytics/queries/11_dedupe_latest.sql:6-21` | Dedupe on a business key with `row_number` and `FILTER` |
| `GolangExercise/offline-sync-app/analytics/seed/seed.sql:13-14` | Deterministic pseudo-random function from `md5` |
| `GolangExercise/offline-sync-app/analytics/analytics_test.go:287-314` | Results must not depend on the session time zone |
| `GolangExercise/offline-sync-app/analytics/analytics_test.go:839-850` | Independent `NOT EXISTS` oracle for the backlog |
| `GolangExercise/offline-sync-app/analytics/EXPLAIN.md:7-11` | Measured before and after table (local, one machine, synthetic) |
| `GolangExercise/offline-sync-app/analytics/indexes.sql:1-5` | The three study indexes and `ANALYZE` |
| `GolangExercise/offline-sync-app/migrations/000002_add_domain_events.up.sql:17-18` | Partial index on unpublished rows |
| `GolangExercise/offline-sync-app/migrations/000002_add_domain_events.up.sql:23-28` | The `processed_events` primary key `(event_id, consumer_name)` |
| `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:68-76` | Mean, median and empty count with LEFT JOIN and `count(s.id)` |
| `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:251-256` | Dashboard metric 1: weekly p99 sync lag |
| `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:264-269` | Dashboard metric 2: stuck outbox rows and oldest age |
| `GolangExercise/offline-sync-app/analytics/QUESTIONS.md:277-284` | Dashboard metric 3: unprocessed events per consumer |

## Self-check

1. Why does `count(*)` after a LEFT JOIN give the wrong answer for a location with no assessments? Because the NULL-extended row counts as one, so I use `count(s.id)`.
2. When does `rank() = 2` return nothing? After a tie for first place, because the ranks go 1, 1, 3.
3. Why can you not average per-group p99 values? Because percentiles do not compose, and on my seed the average of the actor p99 values was about 5.47 hours against a pooled p99 of about 8.74 hours.
4. What is the island trick for consecutive days? `day - row_number()` over one row per actor and day is constant within a streak and changes when a day is skipped.
5. What did the index change in my study, and what did I not measure? Query 1 went from 6.11 ms and 3,063 buffers to 0.105 ms and 10 buffers locally on synthetic data, and I did not measure the write cost on the outbox table.

## What not to claim

- Do not present any seeded number as a finding about a real system: the stuck rows, the notifier stall, the 3 percent duplicates and the offline sync lag are planted by the generator.
- Do not quote the EXPLAIN speed-ups as general results: they are one Postgres 16.15 container, one Apple Silicon laptop, a warm cache, 50,680 rows and a median of six runs.
- Do not claim the write-side cost of the extra indexes: I did not measure it.
- Do not claim I deployed a dashboard: the repo holds the design and three tested queries, not a BI tool.
- Do not claim a skip scan exists or does not exist in a given Postgres version without checking the current docs; the repo note says Postgres 16 has none and says to verify.
- Do not claim the DST bug from my own history: the repo comment records that a two-zone test caught it, and I reproduced the one-hour cutoff shift but found no commit history for the original failure.
- Do not claim the Go tests passed in this session: they reseed the database, so I read them and re-ran the SQL by hand instead.
- Do not call percentiles from pre-aggregated groups correct, and do not call `percentile_cont` an approximation: it is exact and sorts each group.

