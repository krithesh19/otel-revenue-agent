---
name: pickup_pace
description: "Load this skill for questions about booking pace, what changed recently, pickup in the last 7 days, how fast we are booking, or recent reservation activity. Uses get_pickup_delta."
---

# Pickup & Booking Pace Skill

## When to use this skill
Questions like: "What changed in the last 7 days?", "How is our booking pace?", "Are we picking up or slowing down?", "What was booked recently for July?"

## Tool to call
`get_pickup_delta(booking_window_days=7, future_stay_from="YYYY-MM-DD")`

Adjust `booking_window_days` based on the question:
- "last 7 days" → 7
- "last month" → 30
- "last year's booking pace" → 365

## Key principle
Pickup uses `create_datetime` (when the booking was made), NOT `stay_date`.
The question "what was booked this week for July" filters on BOTH:
- `create_datetime` in last 7 days (the booking window)
- `stay_date >= 2026-07-01` (the stay period)

## Interpreting pickup

### Pace signals
- **Strong pickup (room nights growing week-over-week)**: Demand is healthy. Consider tightening rates if OTB is tracking ahead.
- **Weak pickup (fewer new bookings than prior periods)**: Demand softening. Consider promotional activity.
- **Segment-specific pickup**: Check `by_segment` — if OTA is picking up but direct is flat, consider rate parity review.

### Judgment thresholds
- **7-day pickup > 5% of current month OTB**: Strong pace. Hold or increase rates.
- **7-day pickup < 1% of current month OTB within 30 days of arrival**: ⚠️ Last-minute demand weak. Recommended action: open last-minute promotions, push opaque channels.
- **Cancellation-adjusted pickup**: If new bookings < recent cancellations, net OTB is declining. Flag as priority risk.

## Recommended actions
- **Strong pace for future month**: "Demand is strong. Close discounted segments (PROM) for peak dates. Push rate up on OTA."
- **Weak pace for near-term**: "Open PROM and FIT rates. Push last-minute deals on digital channels."
- **Unexpected segment surge**: "New pickup concentrated in one segment — verify it's legitimate demand and not a booking error."

## Common traps
- Do NOT use `stay_date` for the booking window — use `create_datetime`
- Do NOT compare booking window raw numbers without context — 10 new rooms in 7 days means very different things for a hotel that's 20% vs 90% full
