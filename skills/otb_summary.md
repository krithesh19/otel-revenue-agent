---
name: otb_summary
description: "Load this skill for questions about revenue on the books, monthly OTB, total revenue by month, how the hotel is tracking, ADR analysis, or occupancy pacing. Uses get_otb_summary and get_segment_mix."
version: otel-rm-v2
---

# On-the-Books (OTB) Summary Skill

## When to use this skill
Questions like:
- "What revenue is on the books by month?"
- "How is July tracking?"
- "What's our OTB for Q3 2026?"
- "Which month is strongest?"
- "What's our ADR?"

---

## Tool to call

```
get_otb_summary(stay_month="YYYY-MM", exclude_cancelled=True)
```

Default filters (already applied in `vw_stay_night_base`):
- Excludes `reservation_status = 'Cancelled'`
- Excludes `financial_status = 'Provisional'`
- **Always state this assumption in your answer**

---

## Key metrics — what to use and why

| Metric | Field | When to use |
|---|---|---|
| Reservation count | `reservation_count` | Always use this, NEVER `row_count` |
| Room nights | `room_nights` | Occupancy and pace analysis |
| Room revenue | `room_revenue` | Rate/ADR questions |
| Total revenue | `total_revenue` | Broader revenue questions |
| Implied ADR | `room_revenue / room_nights` | Pricing health check |
| Implied occupancy | `room_nights / (98 × days_in_month)` | Demand level |

**98 = total hotel inventory (52 KS + 20 TB + 26 EX)**

---

## Implied ADR interpretation

Compute: `implied_ADR = room_revenue / room_nights`

| ADR scenario | What it means | Action |
|---|---|---|
| ADR consistent across months | Stable pricing | Monitor |
| ADR in group-heavy months lower | Group rate dilution | Review group rate vs BAR |
| ADR dropping month-over-month | Pricing pressure | Rate strategy review |

**Important:** This dataset has no BAR rate target or budget figures loaded.
Do NOT invent or assume ADR targets. Report what the data shows and frame relative to the month's segment mix.

---

## Occupancy interpretation

Compute implied occupancy = `room_nights / (98 × days_in_month)`

| Occupancy | Signal |
|---|---|
| < 30% | Very low — significant unsold inventory |
| 30–60% | Building — typical lead-time range for future months |
| 60–80% | Strong position — rate holding opportunity |
| > 80% | High demand — close discount channels, push rate |

**Note:** For future months, current OTB occupancy will always be below final occupancy — bookings are still coming in. Context matters: 40% OTB at 90 days out is very different from 40% OTB at 7 days out.

---

## Multi-month OTB summary

When the GM asks "revenue by month", call `get_otb_summary` for each relevant month:
- Current month + next 3–4 months is the standard GM briefing window
- Identify the strongest and weakest months
- Flag any month with < 20% implied occupancy as a concern

Always rank months by total_revenue and highlight the top performer and the laggard.

---

## When to cross-reference other skills

After OTB summary, always consider:
- **OTA share > 35%?** → Load `ota_concentration` skill
- **Block share > 40% room nights?** → Load `block_concentration` skill
- **Implied ADR unusually low?** → Check segment mix with `get_segment_mix`
- **GM asks "what's driving this month?"** → Always follow up with `get_segment_mix`

---

## Recommended actions by OTB scenario

| Scenario | Threshold | Recommended action |
|---|---|---|
| Strong OTB | >70% implied occupancy at 60+ days out | Hold rate, close PROM/discounts |
| Moderate OTB | 40–70% occupancy, >30 days out | Monitor weekly, pace is building |
| Weak OTB | <40% occupancy, <30 days out | Open promotions, review rate restrictions |
| Very weak OTB | <20% occupancy, <14 days out | Last-minute promotions, opaque channels |

---

## Common traps

- **NEVER use `row_count` as reservation count** — it overcounts multi-night stays
- **NEVER use `property_date` to filter by month** — always use `stay_date`
- **NEVER include Provisional in OTB briefings** — default view already excludes them
- **NEVER compare to prior year** — this dataset contains 2026 data only; no LY baseline exists
- **NEVER invent ADR targets or budget figures** — only report what the data shows
- **DO state your filters** — always say "Posted, non-cancelled rows only" in your answer
