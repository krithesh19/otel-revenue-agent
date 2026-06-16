---
name: pickup_pace
description: "Load this skill for questions about booking pace, what changed recently, pickup in the last N days, how fast we are booking, recent reservation activity, or whether demand is accelerating or slowing. Uses get_pickup_delta."
version: otel-rm-v2
---

# Pickup & Booking Pace Skill

## When to use this skill
Questions like:
- "What changed in the last 7 days?"
- "How is our booking pace for July?"
- "Are we picking up or slowing down?"
- "What was booked recently for future stays?"
- "Is demand accelerating?"

---

## Tool to call

```
get_pickup_delta(booking_window_days=N, future_stay_from="YYYY-MM-DD")
```

### Window size guide
| Question | booking_window_days | future_stay_from |
|---|---|---|
| "last 7 days" | 7 | today's date |
| "last 2 weeks" | 14 | today's date |
| "last 30 days" | 30 | today's date |
| "recent pickup for July" | 7 | 2026-07-01 |
| "what changed this week for August" | 7 | 2026-08-01 |

---

## Critical: how the booking window works

The tool uses `create_datetime` (stored in UTC) for the booking window — NOT `stay_date`.

**Window boundary logic (important):**
- Window start = Europe/London local midnight, N days ago, converted to UTC
- This correctly handles BST (UTC+1 in summer) vs GMT (UTC+0 in winter)
- Ireland is currently in BST — so "midnight last Monday London time" = 23:00 UTC the previous Sunday

**What this means in practice:**
- "Last 7 days of bookings" = reservations where `create_datetime >= London_midnight_7_days_ago_in_UTC`
- This is already handled by the tool — you do not need to adjust manually
- Just pass `booking_window_days=7` and the tool handles the timezone conversion

---

## Interpreting pickup results

### The context problem
Raw pickup numbers are meaningless without OTB context.
Always frame pickup relative to current OTB:

> "7 new room nights picked up this week — that's 7% of current July OTB (97 room nights), which is a healthy pace at 45 days out."

### Pace signals by scenario

**Strong pickup:**
- New room nights this week > 5% of current month OTB
- Action: Hold or increase rates. Consider closing discounted PROM segment.

**Normal pickup:**
- New room nights 2–5% of current month OTB
- Action: Monitor. No immediate action needed.

**Weak pickup:**
- New room nights < 2% of current month OTB
- Within 30 days of arrival: ⚠️ Last-minute demand softening
- Action: Open PROM and FIT rates. Push last-minute digital promotions.

**Negative net pickup:**
- New bookings < cancellations in the same window
- 🚨 Net OTB is declining — this is a priority alert
- Action: Investigate cancellation source. Emergency rate review.

---

## Judgment thresholds

| Scenario | Threshold | Action |
|---|---|---|
| Strong weekly pace | >5% of OTB added in 7 days | Tighten rates, close discounts |
| Weak near-term pace | <2% of OTB added, <30 days to arrival | Open promotions, push OTA |
| Net negative pickup | Cancellations > new bookings | Emergency review |
| OTA-only pickup | OTA picking up, direct flat | Rate parity audit |
| Single-segment surge | One segment >60% of pickup | Verify legitimacy, check for booking errors |

---

## Segment-level pickup analysis

The tool returns `by_segment` — always check this:
- If Corporate (CGR, CSR) is picking up → healthy, rate-insensitive demand
- If OTA is picking up but direct is flat → possible rate parity issue
- If PROM only → rate promotions are working but margin may be thin
- If nothing is picking up → demand problem, not a rate problem

---

## Cross-skill triggers from pickup

After pickup analysis, check:
- If OTA dominates pickup → load `ota_concentration` skill
- If block/group is picking up heavily → load `block_concentration` skill
- If cancellations are high in the window → load `cancellation_analysis` skill

---

## Common traps

- **NEVER use `stay_date` for pickup window** — use `create_datetime`
- **NEVER report pickup without OTB context** — "10 room nights" means nothing in isolation
- **NEVER compare raw pickup numbers across months** — a 100-room-night month and a 50-room-night month have different velocity expectations
- **DO NOT assume booking window = stay window** — a booking made today can be for any future date
