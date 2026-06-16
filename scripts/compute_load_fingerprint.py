"""
Generate etl/LOAD_PROOF.json from the live database.
Run from project root: python scripts/compute_load_fingerprint.py --output etl/LOAD_PROOF.json
"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def generate_proof(output_path: str):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=0) as conn:
        with conn.cursor() as cur:

            # reservation_stay_status_sha256
            cur.execute("""
                SELECT reservation_id, stay_date::text, financial_status
                FROM public.reservations_hackathon
                ORDER BY reservation_id, stay_date, financial_status
            """)
            rows = cur.fetchall()
            lines = [f"{r['reservation_id']}|{r['stay_date']}|{r['financial_status']}" for r in rows]
            db_fingerprint = hashlib.sha256("\n".join(lines).encode()).hexdigest()
            total_stay_rows = len(rows)

            # posted stay rows
            cur.execute("""
                SELECT COUNT(*) as n FROM public.reservations_hackathon
                WHERE reservation_status <> 'Cancelled' AND financial_status = 'Posted'
            """)
            posted = cur.fetchone()["n"]

            # cancelled reservations
            cur.execute("""
                SELECT COUNT(DISTINCT reservation_id) as n FROM public.reservations_hackathon
                WHERE reservation_status = 'Cancelled'
            """)
            cancelled = cur.fetchone()["n"]

            # total reservations
            cur.execute("SELECT COUNT(DISTINCT reservation_id) as n FROM public.reservations_hackathon")
            total_res = cur.fetchone()["n"]

            # reservation_ids sha256
            cur.execute("""
                SELECT DISTINCT reservation_id FROM public.reservations_hackathon
                ORDER BY reservation_id
            """)
            ids = [r["reservation_id"] for r in cur.fetchall()]
            ids_sha = hashlib.sha256("\n".join(ids).encode()).hexdigest()

            # load manifest
            cur.execute("""
                SELECT dataset_revision, row_hash, scraped_at
                FROM public.load_manifest ORDER BY load_id DESC LIMIT 1
            """)
            manifest = cur.fetchone()

    proof = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_revision": manifest["dataset_revision"] if manifest else None,
        "row_hash": manifest["row_hash"] if manifest else None,
        "scraped_at": manifest["scraped_at"].isoformat() if manifest and manifest["scraped_at"] else None,
        "reservation_stay_status_sha256": db_fingerprint,
        "aggregates": {
            "total_stay_rows": total_stay_rows,
            "posted_stay_rows": int(posted),
            "cancelled_reservations": int(cancelled),
            "total_reservations": int(total_res),
            "reservation_ids_sha256": ids_sha,
        }
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(proof, f, indent=2)

    print(f"✅ LOAD_PROOF.json written to {output_path}")
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="etl/LOAD_PROOF.json")
    args = parser.parse_args()
    generate_proof(args.output)
