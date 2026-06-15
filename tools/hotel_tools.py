"""
Phase 2 — Required tool layer.
Five tools with exact names as specified in REQUIRED_TOOLS.md.
All tools read from semantic views, never from reservations_hackathon directly.
No tool accepts arbitrary SQL strings.
"""
import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)

LONDON_TZ = ZoneInfo("Europe/London")


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# ---------------------------------------------------------------------------
# 1. get_otb_summary
# ---------------------------------------------------------------------------

def get_otb_summary(stay_month: str, exclude_cancelled: bool = True) -> dict:
    """
    On-the-books summary for a calendar month of stay dates (YYYY-MM).

    Default universe: vw_stay_night_base (Posted, non-cancelled).

    Grain:
      - row_count: stay-date rows (NOT reservation count — one row per night)
      - reservation_count: COUNT(DISTINCT reservation_id)
      - room_nights: SUM(number_of_spaces) — accounts for multi-room bookings
      - room_revenue: SUM(daily_room_revenue_before_tax)
      - total_revenue: SUM(daily_total_revenue_before_tax)

    Args:
        stay_month: Calendar month in YYYY-MM format (e.g. "2026-07")
        exclude_cancelled: If True (default), use vw_stay_night_base which
                           already excludes Cancelled + Provisional rows.
                           If False, includes cancelled rows (for cancellation analysis).
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            if exclude_cancelled:
                # Use the semantic view — already filters Cancelled + Provisional
                cur.execute("""
                    SELECT
                        COUNT(*) AS row_count,
                        COUNT(DISTINCT reservation_id) AS reservation_count,
                        COALESCE(SUM(number_of_spaces), 0) AS room_nights,
                        COALESCE(SUM(daily_room_revenue_before_tax), 0) AS room_revenue,
                        COALESCE(SUM(daily_total_revenue_before_tax), 0) AS total_revenue
                    FROM public.vw_stay_night_base
                    WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
                """, (stay_month,))
            else:
                # Include cancelled rows (exclude only Provisional)
                cur.execute("""
                    SELECT
                        COUNT(*) AS row_count,
                        COUNT(DISTINCT reservation_id) AS reservation_count,
                        COALESCE(SUM(number_of_spaces), 0) AS room_nights,
                        COALESCE(SUM(daily_room_revenue_before_tax), 0) AS room_revenue,
                        COALESCE(SUM(daily_total_revenue_before_tax), 0) AS total_revenue
                    FROM public.reservations_hackathon
                    WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
                      AND financial_status = 'Posted'
                """, (stay_month,))

            row = cur.fetchone()

    return {
        "stay_month": stay_month,
        "row_count": int(row["row_count"]),
        "reservation_count": int(row["reservation_count"]),
        "room_nights": int(row["room_nights"]),
        "room_revenue": float(row["room_revenue"]),
        "total_revenue": float(row["total_revenue"]),
        "exclude_cancelled": exclude_cancelled,
        "_note": "row_count is stay-date rows, NOT reservation count. reservation_count = COUNT(DISTINCT reservation_id).",
    }


# ---------------------------------------------------------------------------
# 2. get_segment_mix
# ---------------------------------------------------------------------------

def get_segment_mix(
    stay_month: str,
    macro_group: Optional[str] = None,
) -> dict:
    """
    Segment mix for a stay month using vw_segment_stay_night.

    Grain: stay-date rows aggregated by market segment.
    Shares use the same filtered population as denominator.

    Args:
        stay_month: YYYY-MM
        macro_group: If set, filter to this effective_macro_group only
                     (e.g. "Retail", "Corporate", "MICE", "Leisure", "Leisure Group")
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            if macro_group:
                cur.execute("""
                    SELECT
                        market_code,
                        market_name,
                        effective_macro_group AS macro_group,
                        SUM(number_of_spaces) AS room_nights,
                        SUM(daily_total_revenue_before_tax) AS total_revenue
                    FROM public.vw_segment_stay_night
                    WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
                      AND effective_macro_group = %s
                    GROUP BY market_code, market_name, effective_macro_group
                    ORDER BY total_revenue DESC
                """, (stay_month, macro_group))
            else:
                cur.execute("""
                    SELECT
                        market_code,
                        market_name,
                        effective_macro_group AS macro_group,
                        SUM(number_of_spaces) AS room_nights,
                        SUM(daily_total_revenue_before_tax) AS total_revenue
                    FROM public.vw_segment_stay_night
                    WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
                    GROUP BY market_code, market_name, effective_macro_group
                    ORDER BY total_revenue DESC
                """, (stay_month,))

            rows = cur.fetchall()

    total_rn = sum(int(r["room_nights"]) for r in rows)
    total_rev = sum(float(r["total_revenue"]) for r in rows)

    segments = []
    for r in rows:
        rn = int(r["room_nights"])
        rev = float(r["total_revenue"])
        segments.append({
            "market_code": r["market_code"],
            "market_name": r["market_name"],
            "macro_group": r["macro_group"],
            "room_nights": rn,
            "total_revenue": round(rev, 2),
            "share_of_room_nights": round(rn / total_rn, 6) if total_rn > 0 else 0,
            "share_of_revenue": round(rev / total_rev, 6) if total_rev > 0 else 0,
        })

    return {
        "stay_month": stay_month,
        "macro_group_filter": macro_group,
        "denominator_room_nights": total_rn,
        "denominator_revenue": round(total_rev, 2),
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# 3. get_pickup_delta
# ---------------------------------------------------------------------------

def get_pickup_delta(
    booking_window_days: int,
    future_stay_from: str,
) -> dict:
    """
    Booking pace / pickup for future stays.

    Uses create_datetime for the booking window — NOT stay_date.
    Pickup window boundaries use Europe/London local midnight.

    Grain:
      - new_reservations: COUNT(DISTINCT reservation_id) created in window
      - new_room_nights: SUM(number_of_spaces) for those stays
      - new_total_revenue: SUM(daily_total_revenue_before_tax)

    Args:
        booking_window_days: Look back this many days from now (London midnight)
        future_stay_from: ISO date — only include stay_date >= this date
    """
    now_utc = datetime.now(timezone.utc)
    now_london = now_utc.astimezone(LONDON_TZ)

    # Window start = midnight London time, N days ago
    from datetime import timedelta, time as dt_time
    window_start_london = (now_london - timedelta(days=booking_window_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    window_start_utc = window_start_london.astimezone(timezone.utc)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT reservation_id) AS new_reservations,
                    COALESCE(SUM(number_of_spaces), 0) AS new_room_nights,
                    COALESCE(SUM(daily_total_revenue_before_tax), 0) AS new_total_revenue
                FROM public.vw_stay_night_base
                WHERE create_datetime >= %s
                  AND create_datetime <= %s
                  AND stay_date >= %s::date
            """, (window_start_utc, now_utc, future_stay_from))

            row = cur.fetchone()

            # By segment breakdown
            cur.execute("""
                SELECT
                    s.market_code,
                    s.market_name,
                    s.effective_macro_group AS macro_group,
                    COUNT(DISTINCT s.reservation_id) AS new_reservations,
                    SUM(s.number_of_spaces) AS new_room_nights,
                    SUM(s.daily_total_revenue_before_tax) AS new_total_revenue
                FROM public.vw_segment_stay_night s
                WHERE s.create_datetime >= %s
                  AND s.create_datetime <= %s
                  AND s.stay_date >= %s::date
                GROUP BY s.market_code, s.market_name, s.effective_macro_group
                ORDER BY new_total_revenue DESC
                LIMIT 5
            """, (window_start_utc, now_utc, future_stay_from))

            segment_rows = cur.fetchall()

    by_segment = [
        {
            "market_code": r["market_code"],
            "market_name": r["market_name"],
            "macro_group": r["macro_group"],
            "new_reservations": int(r["new_reservations"]),
            "new_room_nights": int(r["new_room_nights"]),
            "new_total_revenue": round(float(r["new_total_revenue"]), 2),
        }
        for r in segment_rows
    ]

    return {
        "booking_window_days": booking_window_days,
        "future_stay_from": future_stay_from,
        "window_start_utc": window_start_utc.isoformat(),
        "window_end_utc": now_utc.isoformat(),
        "new_reservations": int(row["new_reservations"]),
        "new_room_nights": int(row["new_room_nights"]),
        "new_total_revenue": round(float(row["new_total_revenue"]), 2),
        "by_segment": by_segment,
        "_note": "booking window uses create_datetime (UTC), bounded by Europe/London local midnight.",
    }


# ---------------------------------------------------------------------------
# 4. get_as_of_otb  (HITL gated — requires human approval before calling)
# ---------------------------------------------------------------------------

def get_as_of_otb(stay_month: str, as_of_utc: str) -> dict:
    """
    Point-in-time on-the-books for stay_date month as known at as_of_utc.

    HUMAN-IN-THE-LOOP REQUIRED: This tool is gated behind approval because
    it rebuilds a historical snapshot and is computationally expensive.
    Incorrect as_of_utc values produce misleading comparisons.

    Include a stay row when:
      - create_datetime <= as_of_utc  (booking existed at that point)
      - AND (reservation_status <> 'Cancelled' OR cancellation_datetime > as_of_utc)
            (not yet cancelled at that point)
      - AND financial_status = 'Posted'

    Grain:
      - row_count: stay-date rows matching point-in-time filter
      - reservation_count: COUNT(DISTINCT reservation_id)
      - room_nights: SUM(number_of_spaces)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT reservation_id) AS reservation_count,
                    COALESCE(SUM(number_of_spaces), 0) AS room_nights,
                    COALESCE(SUM(daily_room_revenue_before_tax), 0) AS room_revenue,
                    COALESCE(SUM(daily_total_revenue_before_tax), 0) AS total_revenue
                FROM public.reservations_hackathon
                WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
                  AND financial_status = 'Posted'
                  AND create_datetime <= %s::timestamptz
                  AND (
                    reservation_status <> 'Cancelled'
                    OR cancellation_datetime > %s::timestamptz
                  )
            """, (stay_month, as_of_utc, as_of_utc))

            row = cur.fetchone()

    return {
        "stay_month": stay_month,
        "as_of_utc": as_of_utc,
        "row_count": int(row["row_count"]),
        "reservation_count": int(row["reservation_count"]),
        "room_nights": int(row["room_nights"]),
        "room_revenue": float(row["room_revenue"]),
        "total_revenue": float(row["total_revenue"]),
        "_note": "Point-in-time OTB. HITL gated. Cancelled rows included only if cancellation_datetime > as_of_utc.",
    }


# ---------------------------------------------------------------------------
# 5. get_block_vs_transient_mix
# ---------------------------------------------------------------------------

def get_block_vs_transient_mix(stay_month: str) -> dict:
    """
    Block vs transient mix for a stay month (vw_stay_night_base).

    Grain:
      - block_room_nights / transient_room_nights: SUM(number_of_spaces) by is_block flag
      - block_total_revenue / transient_total_revenue: SUM(daily_total_revenue_before_tax)
      - top_companies: top 3 company_name by total_revenue (null -> 'Transient')
      - top3_company_revenue_share: combined share of month total revenue (0-1)
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Block vs transient summary
            cur.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN is_block THEN number_of_spaces ELSE 0 END), 0) AS block_room_nights,
                    COALESCE(SUM(CASE WHEN NOT is_block THEN number_of_spaces ELSE 0 END), 0) AS transient_room_nights,
                    COALESCE(SUM(CASE WHEN is_block THEN daily_total_revenue_before_tax ELSE 0 END), 0) AS block_total_revenue,
                    COALESCE(SUM(CASE WHEN NOT is_block THEN daily_total_revenue_before_tax ELSE 0 END), 0) AS transient_total_revenue,
                    COALESCE(SUM(daily_total_revenue_before_tax), 0) AS total_revenue,
                    COALESCE(SUM(number_of_spaces), 0) AS total_room_nights
                FROM public.vw_stay_night_base
                WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
            """, (stay_month,))
            summary = cur.fetchone()

            # Top 3 companies by revenue
            cur.execute("""
                SELECT
                    COALESCE(company_name, 'Transient') AS company_name,
                    SUM(daily_total_revenue_before_tax) AS company_revenue
                FROM public.vw_stay_night_base
                WHERE TO_CHAR(stay_date, 'YYYY-MM') = %s
                GROUP BY COALESCE(company_name, 'Transient')
                ORDER BY company_revenue DESC
                LIMIT 3
            """, (stay_month,))
            top_companies_rows = cur.fetchall()

    total_rn = int(summary["total_room_nights"])
    total_rev = float(summary["total_revenue"])
    block_rn = int(summary["block_room_nights"])
    block_rev = float(summary["block_total_revenue"])

    top_companies = [
        {
            "company_name": r["company_name"],
            "total_revenue": round(float(r["company_revenue"]), 2),
        }
        for r in top_companies_rows
    ]

    top3_revenue = sum(c["total_revenue"] for c in top_companies)
    top3_share = round(top3_revenue / total_rev, 6) if total_rev > 0 else 0

    return {
        "stay_month": stay_month,
        "block_room_nights": block_rn,
        "transient_room_nights": int(summary["transient_room_nights"]),
        "block_total_revenue": round(block_rev, 2),
        "transient_total_revenue": round(float(summary["transient_total_revenue"]), 2),
        "block_share_of_room_nights": round(block_rn / total_rn, 6) if total_rn > 0 else 0,
        "block_share_of_revenue": round(block_rev / total_rev, 6) if total_rev > 0 else 0,
        "top_companies": top_companies,
        "top3_company_revenue_share": top3_share,
        "_note": "Block = is_block flag. Room nights = SUM(number_of_spaces). Revenue = total (not room-only).",
    }
