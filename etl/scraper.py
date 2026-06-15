"""
ETL Phase 1 — Extract: Playwright scraper for otel-hackathon-data-site.vercel.app
Scrapes: reservation list (paginated) + detail pages + reference tables
"""
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import async_playwright, Page

BASE_URL = "https://otel-hackathon-data-site.vercel.app"
DATASET_REVISION = "2026.06.12.2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean(text: str) -> Optional[str]:
    t = text.strip()
    return None if t in ("", "—", "-", "null", "None") else t


def parse_bool(text: str) -> bool:
    return text.strip().lower() == "true"


def parse_date(text: str) -> Optional[str]:
    t = clean(text)
    if not t:
        return None
    return t  # already ISO date string from site


def parse_decimal(text: str) -> Optional[float]:
    t = clean(text)
    if not t:
        return None
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def parse_int(text: str) -> Optional[int]:
    t = clean(text)
    if not t:
        return None
    try:
        return int(t.replace(",", ""))
    except ValueError:
        return None


async def wait_for_table(page: Page, timeout: int = 15000):
    """Wait until at least one <tr> with data appears."""
    await page.wait_for_selector("table tbody tr", timeout=timeout)


# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------

async def scrape_reference(page: Page) -> dict:
    print("  Scraping reference tables...")
    await page.goto(f"{BASE_URL}/reference", wait_until="networkidle")
    await asyncio.sleep(2)

    result = {
        "room_types": [],
        "markets": [],
        "channels": [],
        "rate_plans": [],
        "macro_history": [],
    }

    # --- Room types ---
    await page.click("text=Room types")
    await asyncio.sleep(1)
    rows = await page.query_selector_all("table tbody tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) >= 4:
            result["room_types"].append({
                "space_type": clean(await cells[0].inner_text()),
                "room_class": clean(await cells[1].inner_text()),
                "display_name": clean(await cells[2].inner_text()),
                "number_of_rooms": parse_int(await cells[3].inner_text()),
            })

    # --- Markets ---
    await page.click("text=Markets")
    await asyncio.sleep(1)
    rows = await page.query_selector_all("table tbody tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) >= 4:
            result["markets"].append({
                "market_code": clean(await cells[0].inner_text()),
                "market_name": clean(await cells[1].inner_text()),
                "macro_group": clean(await cells[2].inner_text()),
                "description": clean(await cells[3].inner_text()),
            })

    # --- Channels ---
    await page.click("text=Channels")
    await asyncio.sleep(1)
    rows = await page.query_selector_all("table tbody tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) >= 3:
            result["channels"].append({
                "channel_code": clean(await cells[0].inner_text()),
                "channel_name": clean(await cells[1].inner_text()),
                "channel_group": clean(await cells[2].inner_text()),
            })

    # --- Rate plans ---
    await page.click("text=Rate plans")
    await asyncio.sleep(1)
    rows = await page.query_selector_all("table tbody tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) >= 3:
            result["rate_plans"].append({
                "rate_plan_code": clean(await cells[0].inner_text()),
                "plan_family": clean(await cells[1].inner_text()),
                "is_commissionable": parse_bool(await cells[2].inner_text()),
            })

    # --- Macro history ---
    await page.click("text=Macro history")
    await asyncio.sleep(1)
    rows = await page.query_selector_all("table tbody tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) >= 4:
            valid_to = clean(await cells[2].inner_text())
            result["macro_history"].append({
                "market_code": clean(await cells[0].inner_text()),
                "valid_from": clean(await cells[1].inner_text()),
                "valid_to": None if valid_to == "—" else valid_to,
                "macro_group": clean(await cells[3].inner_text()),
            })

    print(f"    Room types: {len(result['room_types'])}")
    print(f"    Markets: {len(result['markets'])}")
    print(f"    Channels: {len(result['channels'])}")
    print(f"    Rate plans: {len(result['rate_plans'])}")
    print(f"    Macro history: {len(result['macro_history'])}")
    return result


# ---------------------------------------------------------------------------
# Reservation list (paginated)
# ---------------------------------------------------------------------------

async def scrape_reservation_list(page: Page) -> list[str]:
    """Return list of all reservation_ids from paginated list."""
    print("  Scraping reservation list...")
    reservation_ids = []
    page_num = 1

    await page.goto(f"{BASE_URL}/reservations", wait_until="networkidle")
    await asyncio.sleep(2)

    while True:
        print(f"    Page {page_num}...")
        await wait_for_table(page)

        rows = await page.query_selector_all("table tbody tr")
        page_ids = []
        for row in rows:
            cells = await row.query_selector_all("td")
            if cells:
                rid = clean(await cells[0].inner_text())
                if rid:
                    page_ids.append(rid)

        reservation_ids.extend(page_ids)
        print(f"      Found {len(page_ids)} reservations on page {page_num}")

        # Try to find next page button
        next_btn = await page.query_selector("button[aria-label='Next page'], a[aria-label='Next'], button:has-text('Next'), a:has-text('Next →')")
        if not next_btn:
            # Try pagination by looking for page numbers
            current_url = page.url
            next_url = f"{BASE_URL}/reservations?page={page_num + 1}"
            await page.goto(next_url, wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Check if we got new data
            new_rows = await page.query_selector_all("table tbody tr")
            if not new_rows or len(new_rows) == 0:
                break
            
            first_cell = await new_rows[0].query_selector("td")
            if first_cell:
                first_id = clean(await first_cell.inner_text())
                if first_id in reservation_ids:
                    break  # We've looped back
            else:
                break
        else:
            is_disabled = await next_btn.get_attribute("disabled")
            if is_disabled is not None:
                break
            await next_btn.click()
            await asyncio.sleep(2)

        page_num += 1
        if page_num > 20:  # Safety limit
            break

    print(f"  Total reservations found: {len(reservation_ids)}")
    return reservation_ids


# ---------------------------------------------------------------------------
# Reservation detail page
# ---------------------------------------------------------------------------

async def scrape_reservation_detail(page: Page, reservation_id: str) -> dict:
    """Scrape a single reservation detail page."""
    await page.goto(f"{BASE_URL}/reservations/{reservation_id}", wait_until="networkidle")
    await asyncio.sleep(1)

    reservation = {"reservation_id": reservation_id, "stay_rows": []}

    # Get all field labels and values
    fields = {}
    
    # Try to get field pairs from the detail card
    labels = await page.query_selector_all("dt, [class*='label'], th")
    values = await page.query_selector_all("dd, [class*='value'], td")

    # More robust: get the entire text content and parse known fields
    page_text = await page.inner_text("body")
    
    # Parse reservation header fields using known field names
    field_map = {
        "arrival_date": r"arrival_date\s*\n([^\n]+)",
        "departure_date": r"departure_date\s*\n([^\n]+)",
        "nights": r"nights\s*\n([^\n]+)",
        "reservation_status": r"reservation_status\s*\n([^\n]+)",
        "create_datetime": r"create_datetime\s*\n([^\n]+)",
        "cancellation_datetime": r"cancellation_datetime\s*\n([^\n]+)",
        "guest_country": r"guest_country\s*\n([^\n]+)",
        "is_block": r"is_block\s*\n([^\n]+)",
        "is_walk_in": r"is_walk_in\s*\n([^\n]+)",
        "number_of_spaces": r"number_of_spaces\s*\n([^\n]+)",
        "space_type": r"space_type\s*\n([^\n]+)",
        "market_code": r"market_code\s*\n([^\n]+)",
        "channel_code": r"channel_code\s*\n([^\n]+)",
        "source_name": r"source_name\s*\n([^\n]+)",
        "rate_plan_code": r"rate_plan_code\s*\n([^\n]+)",
        "adr_room": r"adr_room\s*\n([^\n]+)",
        "lead_time": r"lead_time\s*\n([^\n]+)",
        "company_name": r"company_name\s*\n([^\n]+)",
        "travel_agent_name": r"travel_agent_name\s*\n([^\n]+)",
    }

    for field, pattern in field_map.items():
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            val = clean(match.group(1))
            fields[field] = val

    reservation.update({
        "arrival_date": fields.get("arrival_date"),
        "departure_date": fields.get("departure_date"),
        "nights": parse_int(fields.get("nights", "") or ""),
        "reservation_status": fields.get("reservation_status"),
        "create_datetime": fields.get("create_datetime"),
        "cancellation_datetime": fields.get("cancellation_datetime"),
        "guest_country": fields.get("guest_country"),
        "is_block": parse_bool(fields.get("is_block", "false") or "false"),
        "is_walk_in": parse_bool(fields.get("is_walk_in", "false") or "false"),
        "number_of_spaces": parse_int(fields.get("number_of_spaces", "") or ""),
        "space_type": fields.get("space_type"),
        "market_code": fields.get("market_code"),
        "channel_code": fields.get("channel_code"),
        "source_name": fields.get("source_name"),
        "rate_plan_code": fields.get("rate_plan_code"),
        "adr_room": parse_decimal(fields.get("adr_room", "") or ""),
        "lead_time": parse_int(fields.get("lead_time", "") or ""),
        "company_name": fields.get("company_name"),
        "travel_agent_name": fields.get("travel_agent_name"),
    })

    # Scrape stay rows table
    try:
        await page.wait_for_selector("table tbody tr", timeout=5000)
        rows = await page.query_selector_all("table tbody tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) >= 5:
                reservation["stay_rows"].append({
                    "stay_date": clean(await cells[0].inner_text()),
                    "property_date": clean(await cells[1].inner_text()),
                    "financial_status": clean(await cells[2].inner_text()),
                    "daily_room_revenue_before_tax": parse_decimal(await cells[3].inner_text()),
                    "daily_total_revenue_before_tax": parse_decimal(await cells[4].inner_text()),
                })
    except Exception:
        pass

    return reservation


# ---------------------------------------------------------------------------
# Main extract function
# ---------------------------------------------------------------------------

async def run_extract() -> dict:
    """Run full extraction. Returns all scraped data."""
    scraped_at = datetime.now(timezone.utc).isoformat()
    anchor_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_data = {
        "anchor_date": anchor_date,
        "scraped_at": scraped_at,
        "dataset_revision": DATASET_REVISION,
        "reference": {},
        "reservations": [],
        "reservation_ids": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("Step 1: Scraping reference tables...")
        all_data["reference"] = await scrape_reference(page)

        print("Step 2: Scraping reservation list...")
        reservation_ids = await scrape_reservation_list(page)
        all_data["reservation_ids"] = reservation_ids

        print(f"Step 3: Scraping {len(reservation_ids)} detail pages...")
        for i, rid in enumerate(reservation_ids):
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(reservation_ids)}")
            try:
                detail = await scrape_reservation_detail(page, rid)
                all_data["reservations"].append(detail)
            except Exception as e:
                print(f"  ERROR on {rid}: {e}")

        await browser.close()

    print(f"Extraction complete: {len(all_data['reservations'])} reservations")
    return all_data


def compute_manifest(all_data: dict) -> dict:
    ids = sorted(all_data["reservation_ids"])
    payload = "\n".join(ids).encode("utf-8")
    sha256 = hashlib.sha256(payload).hexdigest()
    return {
        "anchor_date": all_data["anchor_date"],
        "pages_scraped": 3,
        "reservation_ids_count": len(ids),
        "reservation_ids_sha256": sha256,
    }


if __name__ == "__main__":
    import sys
    print("Starting ETL extraction...")
    data = asyncio.run(run_extract())

    # Save raw scraped data
    os.makedirs("etl", exist_ok=True)
    with open("etl/scraped_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print("Saved etl/scraped_data.json")

    # Save manifest
    manifest = compute_manifest(data)
    with open("etl/SCRAPE_MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved etl/SCRAPE_MANIFEST.json — {manifest['reservation_ids_count']} reservations")
