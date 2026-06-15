---
name: otb_summary
description: "Load this skill for questions about revenue on the books, monthly OTB, total revenue by month, or how the hotel is tracking against targets. Uses get_otb_summary."
---

# On-the-Books (OTB) Summary Skill

## When to use this skill
Questions like: "What revenue is on the books?", "How is July tracking?", "What's our OTB for Q3?"

## Tool to call
`get_otb_summary(stay_month="YYYY-MM", exclude_cancelled=True)`

## Interpreting the result

### Key metrics
- `reservation_count` = actual bookings (use this, not `row_count`)
- `room_nights` = total rooms × nights (accounts for multi-room bookings)
- `room_revenue` = room-only revenue before tax
- `total_revenue` = room + packages/breakfast — use for broader questions

### Judgment thresholds
- **ADR check**: compute implied ADR = `room_revenue / room_nights`. If implied ADR is more than 15% below the hotel's BAR rate, flag as a pricing risk.
- **Pace check**: compare current OTB room nights against same month last year. If OTB is more than 20% behind prior year at same point, flag as a pace risk and recommend rate review or promotional push.
- **Revenue concentration**: if a single month accounts for more than 40% of quarterly OTB revenue, flag as concentration risk.

### Recommended actions by scenario
- **Strong OTB (>90% of last year)**: "Hold rate — demand is strong. Consider closing discounted channels."
- **Weak OTB (<70% of last year)**: "Open promotional channels. Review rate restrictions. Consider targeted corporate outreach."
- **Mixed (70-90%)**: "Monitor weekly. Focus pickup analysis on which segments are lagging."

## Common traps to avoid
- Do NOT use `row_count` to report reservations — it overcounts multi-night stays
- Do NOT include Provisional rows in OTB briefings — default filter already excludes them
- Do NOT use `property_date` to filter by month — always use `stay_date`
