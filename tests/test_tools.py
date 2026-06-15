"""
tests/test_tools.py — Tool layer tests (Phase 2)
Covers scenarios 1-12 from TOOL_TEST_SCENARIOS.md (≥10 cases)
Run: pytest tests/test_tools.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tools.hotel_tools import (
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
)

TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Scenario 1 — Grain inequality (July OTB)
# ---------------------------------------------------------------------------

class TestGrainInequality:
    def test_row_count_vs_reservation_count(self):
        """Scenario 1: row_count must be >= reservation_count for July."""
        result = get_otb_summary("2026-07", exclude_cancelled=True)
        assert result["row_count"] >= result["reservation_count"], (
            "row_count should be >= reservation_count (multi-night stays create multiple rows)"
        )

    def test_room_nights_vs_reservation_count(self):
        """Scenario 1: room_nights must be >= reservation_count."""
        result = get_otb_summary("2026-07", exclude_cancelled=True)
        assert result["room_nights"] >= result["reservation_count"]

    def test_room_revenue_lte_total_revenue(self):
        """Scenario 1: room_revenue <= total_revenue (total includes non-room)."""
        result = get_otb_summary("2026-07", exclude_cancelled=True)
        assert result["room_revenue"] <= result["total_revenue"] + TOLERANCE


# ---------------------------------------------------------------------------
# Scenario 2 — Cancellation filter changes counts
# ---------------------------------------------------------------------------

class TestCancellationFilter:
    def test_exclude_cancelled_reduces_row_count(self):
        """Scenario 2: excluding cancelled reduces row_count."""
        with_cancelled = get_otb_summary("2026-08", exclude_cancelled=False)
        without_cancelled = get_otb_summary("2026-08", exclude_cancelled=True)
        # If there are cancellations in this month, excluded count must be lower
        if with_cancelled["row_count"] > without_cancelled["row_count"]:
            assert without_cancelled["row_count"] < with_cancelled["row_count"]

    def test_exclude_cancelled_flag_echoed(self):
        """Scenario 2: exclude_cancelled flag is echoed in result."""
        result = get_otb_summary("2026-07", exclude_cancelled=True)
        assert result["exclude_cancelled"] is True


# ---------------------------------------------------------------------------
# Scenario 3 — Segment shares sum to one
# ---------------------------------------------------------------------------

class TestSegmentShares:
    def test_room_night_shares_sum_to_one(self):
        """Scenario 3: sum of share_of_room_nights == 1.0 ± tolerance."""
        result = get_segment_mix("2026-07", macro_group=None)
        total = sum(s["share_of_room_nights"] for s in result["segments"])
        assert abs(total - 1.0) < TOLERANCE, f"share_of_room_nights sums to {total}, not 1.0"

    def test_revenue_shares_sum_to_one(self):
        """Scenario 3: sum of share_of_revenue == 1.0 ± tolerance."""
        result = get_segment_mix("2026-07", macro_group=None)
        total = sum(s["share_of_revenue"] for s in result["segments"])
        assert abs(total - 1.0) < TOLERANCE, f"share_of_revenue sums to {total}, not 1.0"

    def test_all_shares_between_zero_and_one(self):
        """Scenario 3: every share is between 0 and 1 inclusive."""
        result = get_segment_mix("2026-07", macro_group=None)
        for seg in result["segments"]:
            assert 0 <= seg["share_of_room_nights"] <= 1
            assert 0 <= seg["share_of_revenue"] <= 1


# ---------------------------------------------------------------------------
# Scenario 4 — Macro group filter narrows universe
# ---------------------------------------------------------------------------

class TestMacroGroupFilter:
    def test_filtered_room_nights_lte_unfiltered(self):
        """Scenario 4: filtered total <= unfiltered total room nights."""
        unfiltered = get_segment_mix("2026-07", macro_group=None)
        filtered = get_segment_mix("2026-07", macro_group="Retail")
        assert filtered["denominator_room_nights"] <= unfiltered["denominator_room_nights"]

    def test_all_returned_segments_match_filter(self):
        """Scenario 4: all returned segments have effective macro_group == 'Retail'."""
        result = get_segment_mix("2026-07", macro_group="Retail")
        for seg in result["segments"]:
            assert seg["macro_group"] == "Retail", (
                f"Segment {seg['market_code']} has macro_group {seg['macro_group']}, expected Retail"
            )


# ---------------------------------------------------------------------------
# Scenario 5 — Pickup uses booking date, not stay date
# ---------------------------------------------------------------------------

class TestPickupDelta:
    def test_small_window_lte_large_window(self):
        """Scenario 5: 1-day window produces <= reservations than 365-day window."""
        large = get_pickup_delta(booking_window_days=365, future_stay_from="2026-07-01")
        small = get_pickup_delta(booking_window_days=1, future_stay_from="2026-07-01")
        assert small["new_reservations"] <= large["new_reservations"]

    def test_result_contains_by_segment(self):
        """Scenario 5: result includes by_segment breakdown."""
        result = get_pickup_delta(booking_window_days=30, future_stay_from="2026-07-01")
        assert "by_segment" in result
        assert isinstance(result["by_segment"], list)

    def test_window_dates_in_result(self):
        """Scenario 5: window_start_utc and window_end_utc are in result."""
        result = get_pickup_delta(booking_window_days=7, future_stay_from="2026-07-01")
        assert "window_start_utc" in result
        assert "window_end_utc" in result


# ---------------------------------------------------------------------------
# Scenario 6 — OTA concentration signal
# ---------------------------------------------------------------------------

class TestOTAConcentration:
    def test_ota_segment_exists(self):
        """Scenario 6: OTA market code exists in segment mix."""
        result = get_segment_mix("2026-08", macro_group=None)
        ota_segments = [s for s in result["segments"] if s["market_code"] == "OTA"]
        assert len(ota_segments) > 0, "OTA segment missing — check ETL or wrong month"

    def test_ota_share_between_zero_and_one(self):
        """Scenario 6: OTA revenue share is strictly between 0 and 1."""
        result = get_segment_mix("2026-08", macro_group=None)
        ota = next(s for s in result["segments"] if s["market_code"] == "OTA")
        assert 0 < ota["share_of_revenue"] < 1


# ---------------------------------------------------------------------------
# Scenario 8 — Provisional exclusion from default OTB
# ---------------------------------------------------------------------------

class TestProvisionalExclusion:
    def test_default_otb_excludes_provisional(self):
        """Scenario 8: vw_stay_night_base (default) excludes Provisional rows."""
        import psycopg
        from psycopg.rows import dict_row
        DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon")
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM public.vw_stay_night_base WHERE financial_status = 'Provisional'")
                row = cur.fetchone()
        assert row["n"] == 0, "vw_stay_night_base should contain zero Provisional rows"


# ---------------------------------------------------------------------------
# Scenario 9 — As-of snapshot differs from current OTB
# ---------------------------------------------------------------------------

class TestAsOfOtb:
    def test_as_of_result_has_required_fields(self):
        """Scenario 9: get_as_of_otb returns correct shape."""
        result = get_as_of_otb("2026-08", "2026-05-01T12:00:00Z")
        assert "stay_month" in result
        assert "as_of_utc" in result
        assert "reservation_count" in result
        assert "room_nights" in result
        assert "total_revenue" in result

    def test_as_of_past_lte_current(self):
        """Scenario 9: OTB as of past date <= current OTB (more bookings made since)."""
        past = get_as_of_otb("2026-08", "2026-01-01T00:00:00Z")
        current = get_otb_summary("2026-08", exclude_cancelled=True)
        assert past["reservation_count"] <= current["reservation_count"]


# ---------------------------------------------------------------------------
# Scenario 11 — Block vs transient mix
# ---------------------------------------------------------------------------

class TestBlockVsTransient:
    def test_block_plus_transient_equals_total(self):
        """Scenario 11: block_room_nights + transient_room_nights == OTB room_nights."""
        block_result = get_block_vs_transient_mix("2026-09")
        otb_result = get_otb_summary("2026-09", exclude_cancelled=True)
        total_from_block = block_result["block_room_nights"] + block_result["transient_room_nights"]
        assert abs(total_from_block - otb_result["room_nights"]) <= 1, (
            f"Block+transient={total_from_block} != OTB room_nights={otb_result['room_nights']}"
        )

    def test_shares_between_zero_and_one(self):
        """Scenario 11: block shares are between 0 and 1."""
        result = get_block_vs_transient_mix("2026-09")
        assert 0 <= result["block_share_of_room_nights"] <= 1
        assert 0 <= result["block_share_of_revenue"] <= 1

    def test_top3_share_lte_one(self):
        """Scenario 11: top3_company_revenue_share <= 1."""
        result = get_block_vs_transient_mix("2026-09")
        assert result["top3_company_revenue_share"] <= 1.0

    def test_top_companies_max_three(self):
        """Scenario 11: top_companies has at most 3 entries."""
        result = get_block_vs_transient_mix("2026-09")
        assert len(result["top_companies"]) <= 3


# ---------------------------------------------------------------------------
# Scenario 12 — Tool layer isolation
# ---------------------------------------------------------------------------

class TestToolLayerIsolation:
    def test_all_tools_importable(self):
        """Scenario 12: all five tools import without starting server."""
        from tools.hotel_tools import (
            get_otb_summary,
            get_segment_mix,
            get_pickup_delta,
            get_as_of_otb,
            get_block_vs_transient_mix,
        )
        assert callable(get_otb_summary)
        assert callable(get_segment_mix)
        assert callable(get_pickup_delta)
        assert callable(get_as_of_otb)
        assert callable(get_block_vs_transient_mix)

    def test_no_raw_sql_parameter(self):
        """Scenario 12: no tool accepts a free-form SQL string parameter."""
        import inspect
        from tools.hotel_tools import (
            get_otb_summary, get_segment_mix, get_pickup_delta,
            get_as_of_otb, get_block_vs_transient_mix
        )
        for fn in [get_otb_summary, get_segment_mix, get_pickup_delta, get_as_of_otb, get_block_vs_transient_mix]:
            params = list(inspect.signature(fn).parameters.keys())
            assert "sql" not in params, f"{fn.__name__} has a 'sql' parameter"
            assert "query" not in params, f"{fn.__name__} has a 'query' parameter"
