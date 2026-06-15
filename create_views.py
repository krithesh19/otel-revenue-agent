"""Create semantic views in Supabase."""
import os
import psycopg
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

view1 = """
CREATE OR REPLACE VIEW public.vw_stay_night_base AS
SELECT r.*
FROM public.reservations_hackathon r
WHERE r.reservation_status <> 'Cancelled'
  AND r.financial_status = 'Posted'
"""

view2 = """
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
) h ON TRUE
"""

with psycopg.connect(DATABASE_URL, prepare_threshold=0) as conn:
    conn.execute(view1)
    conn.execute(view2)
    conn.commit()
    print("Views created successfully!")
    
    # Verify
    conn.execute("SELECT COUNT(*) as n FROM public.vw_stay_night_base")
    r = conn.fetchone()
    print(f"vw_stay_night_base: {r[0]} rows")
    
    conn.execute("SELECT COUNT(*) as n FROM public.vw_segment_stay_night")
    r = conn.fetchone()
    print(f"vw_segment_stay_night: {r[0]} rows")
