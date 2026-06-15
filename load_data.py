"""
Direct loader - bypasses old loader.py cache issues.
Run: python load_data.py
"""
import hashlib, json, os, sys
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]
DATASET_REVISION = os.environ.get("DATASET_REVISION", "2026.06.12.2")
SOURCE_URL = "https://otel-hackathon-data-site.vercel.app"

def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=0)

print("Connecting...")
with get_conn() as conn:
    with conn.cursor() as cur:
        print("Truncating...")
        cur.execute("TRUNCATE public.reservations_hackathon CASCADE")
        cur.execute("TRUNCATE public.load_manifest CASCADE")
        cur.execute("TRUNCATE public.market_macro_group_history CASCADE")
        cur.execute("TRUNCATE public.market_code_lookup CASCADE")
        cur.execute("TRUNCATE public.channel_code_lookup CASCADE")
        cur.execute("TRUNCATE public.rate_plan_lookup CASCADE")
        cur.execute("TRUNCATE public.room_type_lookup CASCADE")

        print("Loading data...")
        with open("etl/scraped_data.json") as f:
            data = json.load(f)

        ref = data["reference"]

        # Room types
        for r in ref["room_types"]:
            cur.execute("INSERT INTO public.room_type_lookup (space_type,room_class,display_name,number_of_rooms) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (r["space_type"],r["room_class"],r["display_name"],r["number_of_rooms"]))

        # Rate plans from reference
        for r in ref["rate_plans"]:
            cur.execute("INSERT INTO public.rate_plan_lookup (rate_plan_code,plan_family,is_commissionable) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (r["rate_plan_code"],r["plan_family"],r["is_commissionable"]))

        # Extra rate plans found in data
        extra_plans = [
            ("BARCBB","Retail",False),("BOOKPROM","Retail",True),("DLYBB","Retail",False),
            ("EXPBARB","Retail",True),("EXPBARH","Retail",True),("GOORO","Retail",False),
            ("OCHEARLY","Retail",False),("OCHPERKRO","Retail",False),("CORP10BB","Corporate",False),
            ("EXPP","Retail",True),("ZEPHYR-CORP-25","Corporate",False),
        ]
        for code,family,comm in extra_plans:
            cur.execute("INSERT INTO public.rate_plan_lookup (rate_plan_code,plan_family,is_commissionable) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (code,family,comm))

        # Markets
        for r in ref["markets"]:
            cur.execute("INSERT INTO public.market_code_lookup (market_code,market_name,macro_group,description) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (r["market_code"],r["market_name"],r["macro_group"],r.get("description")))

        # Channels
        for r in ref["channels"]:
            cur.execute("INSERT INTO public.channel_code_lookup (channel_code,channel_name,channel_group) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (r["channel_code"],r["channel_name"],r["channel_group"]))

        # Macro history
        for r in ref["macro_history"]:
            cur.execute("INSERT INTO public.market_macro_group_history (market_code,valid_from,valid_to,macro_group) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (r["market_code"],r["valid_from"],r["valid_to"],r["macro_group"]))

        # Reservations
        total, errors = 0, 0
        for res in data["reservations"]:
            rid = res["reservation_id"]
            if not res.get("arrival_date") or not res.get("stay_rows"):
                errors += 1
                continue
            for stay in res["stay_rows"]:
                if not stay.get("stay_date"):
                    continue
                try:
                    cur.execute("SAVEPOINT s1")
                    cur.execute("""INSERT INTO public.reservations_hackathon
                        (reservation_id,arrival_date,departure_date,stay_date,property_date,
                        reservation_status,financial_status,create_datetime,cancellation_datetime,
                        guest_country,is_block,is_walk_in,number_of_spaces,space_type,
                        market_code,channel_code,source_name,rate_plan_code,
                        daily_room_revenue_before_tax,daily_total_revenue_before_tax,
                        nights,adr_room,lead_time,company_name,travel_agent_name)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (reservation_id,stay_date) DO UPDATE SET
                        financial_status=EXCLUDED.financial_status,
                        daily_room_revenue_before_tax=EXCLUDED.daily_room_revenue_before_tax,
                        daily_total_revenue_before_tax=EXCLUDED.daily_total_revenue_before_tax""",
                        (rid,res["arrival_date"],res["departure_date"],stay["stay_date"],
                        stay.get("property_date") or stay["stay_date"],
                        res.get("reservation_status","Reserved"),
                        stay.get("financial_status","Posted"),
                        res.get("create_datetime"),res.get("cancellation_datetime"),
                        res.get("guest_country"),res.get("is_block",False),
                        res.get("is_walk_in",False),res.get("number_of_spaces",1),
                        res.get("space_type"),res.get("market_code"),res.get("channel_code"),
                        res.get("source_name"),res.get("rate_plan_code"),
                        stay.get("daily_room_revenue_before_tax") or 0,
                        stay.get("daily_total_revenue_before_tax") or 0,
                        res.get("nights",1),res.get("adr_room") or 0,
                        res.get("lead_time") or 0,res.get("company_name"),
                        res.get("travel_agent_name")))
                    cur.execute("RELEASE SAVEPOINT s1")
                    total += 1
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT s1")
                    cur.execute("RELEASE SAVEPOINT s1")
                    errors += 1

        print(f"Inserted {total} stay rows ({errors} errors)")

        # Row hash
        cur.execute("SELECT reservation_id, stay_date::text, financial_status FROM public.reservations_hackathon ORDER BY reservation_id, stay_date, financial_status")
        rows = cur.fetchall()
        lines = [f"{r['reservation_id']}|{r['stay_date']}|{r['financial_status']}" for r in rows]
        row_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()

        # Manifest
        scraped_at = data.get("scraped_at", datetime.now(timezone.utc).isoformat())
        cur.execute("INSERT INTO public.load_manifest (dataset_revision,scraped_at,source_url,row_hash) VALUES (%s,%s,%s,%s)",
            (DATASET_REVISION, scraped_at, SOURCE_URL, row_hash))

        conn.commit()
        print(f"Done! Row hash: {row_hash[:16]}...")

        # Verify counts
        for table in ["reservations_hackathon","room_type_lookup","rate_plan_lookup","market_code_lookup","channel_code_lookup","market_macro_group_history"]:
            cur.execute(f"SELECT COUNT(*) as n FROM public.{table}")
            print(f"  {table}: {cur.fetchone()['n']} rows")
