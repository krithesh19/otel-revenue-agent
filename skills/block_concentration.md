---
name: block_concentration
description: "Load this skill for questions about group business, block bookings, conference demand, corporate groups, concentration risk, or whether the hotel has too much group business. Uses get_block_vs_transient_mix."
---

# Block & Group Concentration Skill

## When to use this skill
Questions like: "How much group business do we have?", "Is our business concentrated in a few large bookings?", "What's our group vs transient split?", "Which companies are driving revenue?"

## Tool to call
`get_block_vs_transient_mix(stay_month="YYYY-MM")`

## Judgment thresholds (critical)

### Block concentration risk levels
- **Block share of room nights < 20%**: Low group. Hotel is transient-driven. Good flexibility on pricing. Risk: vulnerable to transient demand softness.
- **Block share of room nights 20–40%**: Balanced mix. Healthy foundation of group with transient upside.
- **Block share of room nights > 40%**: ⚠️ HIGH GROUP CONCENTRATION. Risk: if a large group cancels, significant revenue at risk. Recommended action: review cancellation clauses, ensure attrition penalties are in place, maintain transient inventory.
- **Block share of room nights > 60%**: 🚨 CRITICAL. Hotel is over-committed to group. Transient upside is constrained. If group cancels, recovery options are limited at short lead times.

### Company concentration risk
- **Top 3 companies > 50% of revenue**: Dangerous concentration. Single client risk. Recommended action: diversify corporate accounts, reduce dependency on top client.
- **Top 3 companies 30–50%**: Moderate concentration. Monitor closely.
- **Top 3 companies < 30%**: Healthy spread of business.

### Single block risk
If one company accounts for > 25% of a single month's revenue, flag as single-block risk. Check the cancellation policy attached to that reservation.

## Recommended actions by scenario
- **High block + top company > 25%**: "Review block contract terms. Ensure attrition clause covers 80%+ of committed room nights. Consider whether transient inventory is sufficient for walk-in demand."
- **Low block (<20%)**: "Explore MICE/corporate group RFPs for shoulder months. Group business provides revenue certainty."
- **Balanced mix**: "Hold current strategy. Monitor block pickup weekly during 90-day window."

## Common traps
- Do NOT confuse `is_block` with `market_code IN ('CGR','CNI','SMERF')` — `is_block` is the correct flag
- Do NOT use reservation count for mix analysis — use room nights (`SUM(number_of_spaces)`)
