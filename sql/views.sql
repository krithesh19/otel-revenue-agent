-- Semantic views for Phase 2
-- These views sit between raw tables and agent-facing tools.
-- Tools must NOT query reservations_hackathon directly.

CREATE OR REPLACE VIEW public.vw_stay_night_base AS
SELECT
  r.*
FROM public.reservations_hackathon r
WHERE r.reservation_status <> 'Cancelled'
  AND r.financial_status = 'Posted';

CREATE OR REPLACE VIEW public.vw_segment_stay_night AS
SELECT
  b.*,
  COALESCE(h.macro_group, m.macro_group) AS effective_macro_group,
  m.market_name
FROM public.vw_stay_night_base b
JOIN public.market_code_lookup m ON m.market_code = b.market_code
LEFT JOIN LATERAL (
  SELECT h.macro_group
  FROM public.market_macro_group_history h
  WHERE h.market_code = b.market_code
    AND b.stay_date >= h.valid_from
    AND (h.valid_to IS NULL OR b.stay_date < h.valid_to)
  ORDER BY h.valid_from DESC
  LIMIT 1
) h ON TRUE;
