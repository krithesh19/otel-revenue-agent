"""
ETL Phase 1 — Load: Transform scraped data and load into Postgres.
Idempotent: truncate-and-reload on every run.
Fixed: uses SAVEPOINT per row to handle individual insert errors.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)
DATASET_REVISION = os.environ.get("DATASET_REVISION", "2026.06.12.2")
SOURCE_URL = "https://otel-hackathon-data-site.vercel.app"


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=0)


def truncate_all(cur):
    print("  Truncating tables...")
    cur.execute("TRUNCATE public.reservations_hackathon CASCADE")
    cur.execute("TRUNCATE public.load_manifest CASCADE")
    cur.execute("TRUNCATE public.market_macro_group_history CASCADE")
    cur.execute("TRUNCATE public.market_code_lookup CASCADE")
    cur.execute("TRUNCATE public.channel_code_lookup CASCADE") 
    cur.execute("TRUNCATE public.room_type_lookup CASCADE")


def load_reference(cur, reference: dict):
    print("  Loading room_type_lookup...")
    for row in reference["room_types"]:
        cur.execute("""
            INSERT INTO public.room_type_lookup
              (space_type, room_class, display_name, number_of_rooms)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (space_type) DO UPDATE SET
              room_class = EXCLUDED.room_class,
              display_name = EXCLUDED.display_name,
              number_of_rooms = EXCLUDED.number_of_rooms
        """, (row["space_type"], row["room_class"], row["display_name"], row["number_of_rooms"]))

    print("  Loading rate_plan_lookup...")
    for row in reference["rate_plans"]:
        cur.execute("""
            INSERT INTO public.rate_plan_lookup
              (rate_plan_code, plan_family, is_commissionable)
            VALUES (%s, %s, %s)
            ON CONFLICT (rate_plan_code) DO UPDATE SET
              plan_family = EXCLUDED.plan_family,
              is_commissionable = EXCLUDED.is_commissionable
        """, (row["rate_plan_code"], row["plan_family"], row["is_commissionable"]))

    print("  Loading market_code_lookup...")
    for row in reference["markets"]:
        cur.execute("""
            INSERT INTO public.market_code_lookup
              (market_code, market_name, macro_group, description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (market_code) DO UPDATE SET
              market_name = EXCLUDED.market_name,
              macro_group = EXCLUDED.macro_group,
              description = EXCLUDED.description
        """, (row["market_code"], row["market_name"], row["macro_group"], row.get("description")))

    print("  Loading channel_code_lookup...")
    for row in reference["channels"]:
        cur.execute("""
            INSERT INTO public.channel_code_lookup
              (channel_code, channel_name, channel_group)
            VALUES (%s, %s, %s)
            ON CONFLICT (channel_code) DO UPDATE SET
              channel_name = EXCLUDED.channel_name,
              channel_group = EXCLUDED.channel_group
        """, (row["channel_code"], row["channel_name"], row["channel_group"]))

    print("  Loading market_macro_group_history...")
    for row in reference["macro_history"]:
        cur.execute("""
            INSERT INTO public.market_macro_group_history
              (market_code, valid_from, valid_to, macro_group)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (market_code, valid_from) DO UPDATE SET
              valid_to = EXCLUDED.valid_to,
              macro_group = EXCLUDED.macro_group
        """, (row["market_code"], row["valid_from"], row["valid_to"], row["macro_group"]))


def load_reservations(cur, reservations: list) -> int:
    print(f"  Loading {len(reservations)} reservations...")
    total_rows = 0
    errors = 0

    for res in reservations:
        rid = res["reservation_id"]
        if not res.get("arrival_date") or not res.get("stay_rows"):
            errors += 1
            continue

        for stay in res["stay_rows"]:
            if not stay.get("stay_date"):
                continue
            try:
                cur.execute("SAVEPOINT row_insert")
                cur.execute("""
                    INSERT INTO public.reservations_hackathon (
                        reservation_id, arrival_date, departure_date, stay_date,
                        property_date, reservation_status, financial_status,
                        create_datetime, cancellation_datetime, guest_country,
                        is_block, is_walk_in, number_of_spaces, space_type,
                        market_code, channel_code, source_name, rate_plan_code,
                        daily_room_revenue_before_tax, daily_total_revenue_before_tax,
                        nights, adr_room, lead_time, company_name, travel_agent_name
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s
                    )
                    ON CONFLICT (reservation_id, stay_date) DO UPDATE SET
                        financial_status = EXCLUDED.financial_status,
                        daily_room_revenue_before_tax = EXCLUDED.daily_room_revenue_before_tax,
                        daily_total_revenue_before_tax = EXCLUDED.daily_total_revenue_before_tax,
                        property_date = EXCLUDED.property_date
                """, (
                    rid,
                    res["arrival_date"],
                    res["departure_date"],
                    stay["stay_date"],
                    stay.get("property_date") or stay["stay_date"],
                    res.get("reservation_status", "Reserved"),
                    stay.get("financial_status", "Posted"),
                    res.get("create_datetime"),
                    res.get("cancellation_datetime"),
                    res.get("guest_country"),
                    res.get("is_block", False),
                    res.get("is_walk_in", False),
                    res.get("number_of_spaces", 1),
                    res.get("space_type"),
                    res.get("market_code"),
                    res.get("channel_code"),
                    res.get("source_name"),
                    res.get("rate_plan_code"),
                    stay.get("daily_room_revenue_before_tax") or 0,
                    stay.get("daily_total_revenue_before_tax") or 0,
                    res.get("nights", 1),
                    res.get("adr_room") or 0,
                    res.get("lead_time") or 0,
                    res.get("company_name"),
                    res.get("travel_agent_name"),
                ))
                cur.execute("RELEASE SAVEPOINT row_insert")
                total_rows += 1
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT row_insert")
                cur.execute("RELEASE SAVEPOINT row_insert")
                print(f"    ERROR {rid}/{stay.get('stay_date')}: {e}")
                errors += 1

    print(f"  Inserted {total_rows} stay rows ({errors} errors)")
    return total_rows


def compute_row_hash(cur) -> str:
    cur.execute("""
        SELECT reservation_id, stay_date::text, financial_status
        FROM public.reservations_hackathon
        ORDER BY reservation_id, stay_date, financial_status
    """)
    rows = cur.fetchall()
    lines = [f"{r['reservation_id']}|{r['stay_date']}|{r['financial_status']}" for r in rows]
    payload = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_load_manifest(cur, row_hash: str, scraped_at: str):
    cur.execute("""
        INSERT INTO public.load_manifest
          (dataset_revision, scraped_at, source_url, row_hash)
        VALUES (%s, %s, %s, %s)
    """, (DATASET_REVISION, scraped_at, SOURCE_URL, row_hash))


def run_load(scraped_data_path: str = "etl/scraped_data.json"):
    print(f"Loading from {scraped_data_path}...")
    with open(scraped_data_path) as f:
        data = json.load(f)

    scraped_at = data.get("scraped_at", datetime.now(timezone.utc).isoformat())

    with get_conn() as conn:
        with conn.cursor() as cur:
            truncate_all(cur)
            load_reference(cur, data["reference"])
            load_reservations(cur, data["reservations"])
            row_hash = compute_row_hash(cur)
            write_load_manifest(cur, row_hash, scraped_at)
            conn.commit()

    print(f"Load complete. Row hash: {row_hash[:16]}...")
    return row_hash


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    path = sys.argv[1] if len(sys.argv) > 1 else "etl/scraped_data.json"
    run_load(path)
