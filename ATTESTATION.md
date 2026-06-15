# ATTESTATION.md (Phase 0)

## Candidate

- Name: Kritheshvar Vinothkumar
- Repository URL: https://github.com/krithesh19/otel-revenue-agent
- Date: 2026-06-15

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> One row per reservation × stay_date: a 3-night reservation creates 3 rows, each representing one night of that stay.

### 2. Revenue columns

Name the two revenue columns and when to use each.

> `daily_room_revenue_before_tax` — use when the question is specifically about room revenue only. `daily_total_revenue_before_tax` — use for broader revenue questions that include packages, breakfast, or other non-room components.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> "How many reservations were made in July?" — counting rows would overcount because a 3-night reservation produces 3 rows; the correct answer requires `COUNT(DISTINCT reservation_id)`.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> No. There is no `otel_challenge_token` column in `schema.sql`. This field does not exist in the official schema.

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Excluded from default OTB: `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`. Default OTB universe is Posted + non-cancelled rows only.

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> `property_date` can differ from `stay_date` on night-boundary or audit rows where the hotel's business date attribution differs from the physical stay night. Monthly OTB should always be driven by `stay_date`, not `property_date`.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> In `get_as_of_otb`, a cancelled reservation is included if its `cancellation_datetime > as_of_utc` — meaning it had not yet been cancelled at the point-in-time snapshot. Bookings with `create_datetime > as_of_utc` are excluded as they did not exist yet.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> `is_block = true` identifies group/block reservations (conferences, corporate groups, events). Filtering `is_block = true` gives group business; `is_block = false` gives transient business. This is the correct flag to use for mix analysis, not `market_code` alone.

### 9. List pagination

How many reservations does the data site show per list page?

> 100 reservations per page (254 total reservations across 3 pages, confirmed on the live site).

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> After scraping, `reservation_ids_count` in `SCRAPE_MANIFEST.json` is compared against `total_reservations` on `/verify` (254). The SHA-256 of sorted reservation IDs is also compared. `compute_load_fingerprint.py` provides a second cross-check against the live database.

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> `row_count` is the number of stay-date rows in `vw_stay_night_base` for the month — one per reservation × night. `reservation_count` is `COUNT(DISTINCT reservation_id)` — the actual number of unique bookings. A 3-night reservation contributes 3 to `row_count` but only 1 to `reservation_count`.

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> `get_as_of_otb` rebuilds a point-in-time snapshot by scanning the full reservation history, which is computationally expensive and can produce misleading numbers if triggered accidentally (e.g. wrong `as_of_utc` date). Gating it behind HITL approval ensures the GM explicitly confirms the snapshot date before the agent runs the expensive query, preventing silent incorrect comparisons.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> "Are we too dependent on OTA?" — this loads the `ota_concentration` skill which defines the judgment threshold (OTA share > 35% of revenue = high dependency risk with recommended action to diversify), then calls `get_segment_mix` to get the actual numbers to evaluate against that threshold.

---

## ETL design (one line)

> Playwright paginates `/reservations?page=N` (100 per page, 3 pages), drills into each `/reservations/{id}` detail page for stay rows + financial_status; idempotency via truncate-and-reload on every run; anchor date is today's UTC date (2026-06-15), scraped and reconciled against `/verify` on the same calendar day before submission.
