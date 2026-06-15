"""Fix missing rate plan codes in rate_plan_lookup."""
import os
import psycopg
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

missing_rate_plans = [
    ("BARCBB", "Retail", False),
    ("BOOKPROM", "Retail", True),
    ("DLYBB", "Retail", False),
    ("EXPBARB", "Retail", True),
    ("EXPBARH", "Retail", True),
    ("GOORO", "Retail", False),
    ("OCHEARLY", "Retail", False),
    ("OCHPERKRO", "Retail", False),
]

with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        for code, family, comm in missing_rate_plans:
            cur.execute("""
                INSERT INTO public.rate_plan_lookup (rate_plan_code, plan_family, is_commissionable)
                VALUES (%s, %s, %s)
                ON CONFLICT (rate_plan_code) DO NOTHING
            """, (code, family, comm))
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM public.rate_plan_lookup")
        count = cur.fetchone()
        print(f"Done! rate_plan_lookup now has {count[0]} rows")
