"""
ETL main entry point.
Run: python etl/run_etl.py
"""
import asyncio
import os
import sys

# Load .env
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.scraper import run_extract, compute_manifest
from etl.loader import run_load
import json

async def main():
    print("=" * 60)
    print("OTEL REVENUE AGENT — ETL PIPELINE")
    print("=" * 60)

    # Step 1: Extract
    print("\n[PHASE 1] EXTRACT — Scraping data site...")
    data = await run_extract()

    # Save raw data
    os.makedirs("etl", exist_ok=True)
    with open("etl/scraped_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved etl/scraped_data.json")

    # Save manifest
    manifest = compute_manifest(data)
    with open("etl/SCRAPE_MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved etl/SCRAPE_MANIFEST.json")
    print(f"  Reservations: {manifest['reservation_ids_count']}")
    print(f"  SHA256: {manifest['reservation_ids_sha256'][:16]}...")

    # Step 2: Load
    print("\n[PHASE 2] LOAD — Inserting into Postgres...")
    run_load("etl/scraped_data.json")

    print("\n" + "=" * 60)
    print("ETL COMPLETE")
    print("Next step: python scripts/compute_load_fingerprint.py --output etl/LOAD_PROOF.json")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
