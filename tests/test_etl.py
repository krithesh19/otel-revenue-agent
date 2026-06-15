"""
tests/test_etl.py — ETL property tests (Phase 1)
Covers scenarios 1-4 from ETL_TEST_SCENARIOS.md
Run: pytest tests/test_etl.py -v
Requires: loaded Postgres DB (docker compose up + python etl/run_etl.py)
"""
import json
import os
import hashlib
import pytest
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)


@pytest.fixture(scope="module")
def conn():
    c = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    yield c
    c.close()


def query_one(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def query_all(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Scenario 1 — Lookup row counts
# ---------------------------------------------------------------------------

class TestLookupRowCounts:
    def test_room_type_lookup_count(self, conn):
        """room_type_lookup must have exactly 3 rows."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.room_type_lookup")
        assert row["n"] == 3, f"Expected 3 room types, got {row['n']}"

    def test_rate_plan_lookup_count(self, conn):
        """rate_plan_lookup must have exactly 8 rows."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.rate_plan_lookup")
        assert row["n"] == 8, f"Expected 8 rate plans, got {row['n']}"

    def test_market_code_lookup_count(self, conn):
        """market_code_lookup must have exactly 10 rows."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.market_code_lookup")
        assert row["n"] == 10, f"Expected 10 market codes, got {row['n']}"

    def test_market_macro_group_history_count(self, conn):
        """market_macro_group_history must have exactly 11 rows."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.market_macro_group_history")
        assert row["n"] == 11, f"Expected 11 macro history rows, got {row['n']}"

    def test_channel_code_lookup_count(self, conn):
        """channel_code_lookup must have exactly 4 rows."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.channel_code_lookup")
        assert row["n"] == 4, f"Expected 4 channels, got {row['n']}"


# ---------------------------------------------------------------------------
# Scenario 2 — Fact-table grain uniqueness
# ---------------------------------------------------------------------------

class TestFactTableGrain:
    def test_no_duplicate_reservation_stay_date(self, conn):
        """No duplicate (reservation_id, stay_date) pairs."""
        row = query_one(conn, """
            SELECT COUNT(*) AS dups FROM (
                SELECT reservation_id, stay_date, COUNT(*) AS n
                FROM public.reservations_hackathon
                GROUP BY reservation_id, stay_date
                HAVING COUNT(*) > 1
            ) sub
        """)
        assert row["dups"] == 0, f"Found {row['dups']} duplicate (reservation_id, stay_date) pairs"

    def test_total_reservations_count(self, conn):
        """Should have 254 distinct reservations."""
        row = query_one(conn, "SELECT COUNT(DISTINCT reservation_id) AS n FROM public.reservations_hackathon")
        assert row["n"] == 254, f"Expected 254 distinct reservations, got {row['n']}"

    def test_total_stay_rows_count(self, conn):
        """Should have 542 total stay rows (from /verify)."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.reservations_hackathon")
        assert row["n"] == 542, f"Expected 542 stay rows, got {row['n']}"


# ---------------------------------------------------------------------------
# Scenario 3 — Manifest and verify reconciliation
# ---------------------------------------------------------------------------

class TestManifestReconciliation:
    def test_manifest_exists(self):
        """SCRAPE_MANIFEST.json must exist."""
        assert os.path.exists("etl/SCRAPE_MANIFEST.json"), "etl/SCRAPE_MANIFEST.json not found"

    def test_manifest_reservation_count_matches_db(self, conn):
        """Manifest reservation_ids_count must match DB distinct count."""
        with open("etl/SCRAPE_MANIFEST.json") as f:
            manifest = json.load(f)
        db_row = query_one(conn, "SELECT COUNT(DISTINCT reservation_id) AS n FROM public.reservations_hackathon")
        assert manifest["reservation_ids_count"] == db_row["n"], (
            f"Manifest count {manifest['reservation_ids_count']} != DB count {db_row['n']}"
        )

    def test_manifest_sha256_matches_db(self, conn):
        """Manifest SHA256 must match computed hash of sorted DB reservation IDs."""
        with open("etl/SCRAPE_MANIFEST.json") as f:
            manifest = json.load(f)

        rows = query_all(conn, """
            SELECT DISTINCT reservation_id FROM public.reservations_hackathon ORDER BY reservation_id
        """)
        ids = [r["reservation_id"] for r in rows]
        computed = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()

        assert manifest["reservation_ids_sha256"] == computed, (
            f"Manifest SHA256 mismatch.\nManifest: {manifest['reservation_ids_sha256']}\nComputed: {computed}"
        )

    def test_load_manifest_populated(self, conn):
        """load_manifest must have at least one row."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.load_manifest")
        assert row["n"] >= 1, "load_manifest is empty — ETL did not record a run"

    def test_dataset_revision_in_manifest(self, conn):
        """dataset_revision in load_manifest must match expected revision."""
        row = query_one(conn, "SELECT dataset_revision FROM public.load_manifest ORDER BY load_id DESC LIMIT 1")
        assert row["dataset_revision"] is not None, "dataset_revision is null in load_manifest"


# ---------------------------------------------------------------------------
# Scenario 4 (bonus) — Stay row expansion grain check
# ---------------------------------------------------------------------------

class TestStayRowExpansion:
    def test_multi_night_stay_row_count(self, conn):
        """For multi-night reservations, row count should equal nights field."""
        rows = query_all(conn, """
            SELECT reservation_id, nights, COUNT(*) AS row_count
            FROM public.reservations_hackathon
            WHERE nights > 1
            GROUP BY reservation_id, nights
            HAVING COUNT(*) != nights
        """)
        assert len(rows) == 0, (
            f"Found {len(rows)} reservations where row_count != nights: "
            f"{[dict(r) for r in rows[:3]]}"
        )

    def test_financial_status_values(self, conn):
        """financial_status must only be Posted or Provisional."""
        rows = query_all(conn, """
            SELECT DISTINCT financial_status FROM public.reservations_hackathon
            WHERE financial_status NOT IN ('Posted', 'Provisional')
        """)
        assert len(rows) == 0, f"Unexpected financial_status values: {rows}"

    def test_provisional_row_count(self, conn):
        """Should have 5 provisional rows (from /verify)."""
        row = query_one(conn, "SELECT COUNT(*) AS n FROM public.reservations_hackathon WHERE financial_status = 'Provisional'")
        assert row["n"] == 5, f"Expected 5 provisional rows, got {row['n']}"

    def test_cancelled_reservation_count(self, conn):
        """Should have 22 cancelled reservations (from /verify)."""
        row = query_one(conn, "SELECT COUNT(DISTINCT reservation_id) AS n FROM public.reservations_hackathon WHERE reservation_status = 'Cancelled'")
        assert row["n"] == 22, f"Expected 22 cancelled reservations, got {row['n']}"
