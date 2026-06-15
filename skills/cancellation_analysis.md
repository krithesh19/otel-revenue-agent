---
name: cancellation_analysis
description: "Load this skill for questions about cancellations, how much business was cancelled, cancellation rates, or cancellation trends. Uses get_otb_summary with exclude_cancelled=False."
---

# Cancellation Analysis Skill

## When to use this skill
Questions like: "How much business was cancelled in June?", "What's our cancellation rate?", "Are cancellations increasing?"

## Tool to call
Call `get_otb_summary` twice:
1. `get_otb_summary(stay_month="YYYY-MM", exclude_cancelled=True)` — current live OTB
2. `get_otb_summary(stay_month="YYYY-MM", exclude_cancelled=False)` — total including cancelled

Cancelled reservations = result_2.reservation_count - result_1.reservation_count
Cancellation rate = cancelled / total_ever_booked

## Judgment thresholds

### Cancellation rate benchmarks
- **Cancellation rate < 10%**: Low. Healthy booking behaviour. Typically direct/corporate business.
- **Cancellation rate 10–20%**: Normal for OTA-heavy hotels (OTA bookings have higher cancel rates due to free cancellation policies).
- **Cancellation rate > 20%**: ⚠️ Elevated. Review cancellation policies. Consider non-refundable rate promotions.
- **Cancellation rate > 30%**: 🚨 High. Significant revenue at risk. Recommended action: shift mix toward non-refundable rates, tighten OTA free cancellation window, review deposit policy.

### Revenue at risk from cancellations
Cancelled revenue = SUM(daily_total_revenue_before_tax) of cancelled rows.
If cancelled revenue > 15% of total-ever-booked revenue, flag as material risk.

## Recommended actions
- **High OTA cancellations**: "Push non-refundable advance purchase rates on OTA. Shift mix to direct bookings with deposit requirements."
- **High cancellations near arrival**: "Last-minute cancellations suggest demand softness or better alternatives available. Review rate competitiveness."
- **Corporate cancellations**: "Review corporate contract terms. Consider minimum commitment clauses for high-volume accounts."

## Common traps
- Cancelled rows still exist in the database — `reservation_status = 'Cancelled'`
- Do NOT exclude cancelled rows when answering cancellation questions
- `cancellation_datetime` tells you WHEN it was cancelled — use for trend analysis
- Cancelled room nights were never actually consumed — do not include in occupancy calculations
