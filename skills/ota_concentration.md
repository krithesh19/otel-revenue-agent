---
name: ota_concentration
description: "Load this skill for questions about OTA dependency, channel mix, whether the hotel is too reliant on Booking.com or Expedia, or distribution risk. Uses get_segment_mix."
---

# OTA Concentration & Channel Mix Skill

## When to use this skill
Questions like: "Are we too dependent on OTA?", "What's our channel mix?", "How much is coming from Booking.com vs direct?"

## Tool to call
`get_segment_mix(stay_month="YYYY-MM", macro_group=None)`
Then filter results to `market_code == "OTA"` and compare against total.

## Judgment thresholds (critical)

### OTA dependency risk levels
- **OTA share of revenue < 25%**: Healthy. Direct and corporate channels are strong. No action needed.
- **OTA share of revenue 25–35%**: Watch zone. Monitor trend direction. Consider direct booking incentives.
- **OTA share of revenue > 35%**: ⚠️ HIGH DEPENDENCY RISK. Recommended action: close lowest-rate OTA channels, push direct booking promotions, negotiate better net rates with OTA partners.
- **OTA share of revenue > 50%**: 🚨 CRITICAL. The hotel is over-reliant on a single expensive channel. Immediate action: revenue manager review, rate parity audit, loyalty programme push.

### Commission cost context
OTA bookings via WEB channel are typically commissionable (8–15% of revenue). Every 10% shift from OTA to direct saves approximately 1–1.5% of total revenue in commission.

### Healthy channel mix target
- OTA: 20–30% of revenue
- Direct (BAR, PROM via REC channel): 30–40%
- Corporate (CSR, CNR): 20–30%
- Group/MICE: 10–20%

## Recommended actions
- **If OTA > 35%**: "Close BAR channel on OTAs for peak dates. Push Brand website rate. Consider a direct booking offer for loyalty members."
- **If Direct < 20%**: "Review rate parity — direct rate may be uncompetitive. Audit metasearch presence."
- **If Corporate < 15%**: "Identify lapsed corporate accounts. Outreach to top 10 companies by prior year room nights."

## Common traps
- Do NOT confuse OTA market code with WEB channel — OTA is the segment, WEB is the booking channel. They overlap but are not identical.
- Do NOT use static `macro_group` from market_code_lookup for PROM — use effective macro group (PROM reclassified to Leisure Group from 2025-06-01).
