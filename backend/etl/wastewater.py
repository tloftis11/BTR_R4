"""ETL: CDC Wastewater Viral Activity Level -> fact_observation.

Source: https://data.cdc.gov/resource/atcp-73re.json (dim_source id=1)
Weekly per-site Wastewater Viral Activity Level (WVAL, 0-10 scale) for
SARS-CoV-2, Influenza A, and RSV. Verified current as of 2026-09-18
(max week_end observed: 2026-09-12) -- see seed/seed_sources.py notes for why
this replaced the originally-researched dataset, which had gone stale.

Geography: this dataset gives state name + county name (text), no FIPS --
mapped here to state-level dim_geo rows. County name is preserved in
raw_payload for a future county-level enrichment pass.

Run: uv run python -m etl.wastewater [--weeks N]
"""

import argparse
import json
from datetime import date, datetime, timedelta

import httpx

from db import get_connection
from seed.seed_geo import STATE_NAMES

DATASET_URL = "https://data.cdc.gov/resource/atcp-73re.json"
SOURCE_ID = 1  # CDC Wastewater Viral Activity Level, see seed/seed_sources.py
PAGE_SIZE = 5000

# pathogen_target (source text) -> dim_pathogen.canonical_name
PATHOGEN_MAP = {
    "SARS-CoV-2": "SARS-CoV-2",
    "Influenza A virus": "Influenza A",
    "RSV": "RSV",
}

STATE_NAME_TO_ABBR = {full_name.lower(): abbr for abbr, full_name in STATE_NAMES.items()}


def fetch_records(since: date) -> list[dict]:
    """Page through the Socrata API for all records with week_end >= since."""
    records: list[dict] = []
    offset = 0
    while True:
        resp = httpx.get(
            DATASET_URL,
            params={
                "$limit": PAGE_SIZE,
                "$offset": offset,
                "$where": f"week_end >= '{since.isoformat()}'",
                "$order": "week_end",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        records.extend(page)
        offset += PAGE_SIZE
        if len(page) < PAGE_SIZE:
            break
    return records


def load_geo_lookup(con) -> dict[str, int]:
    """state abbreviation -> geo_id, from the already-seeded dim_geo state rows."""
    rows = con.execute("SELECT geo_code, geo_id FROM dim_geo WHERE geo_type = 'state'").fetchall()
    return {code: geo_id for code, geo_id in rows}


def load_pathogen_lookup(con) -> dict[str, int]:
    rows = con.execute("SELECT canonical_name, pathogen_id FROM dim_pathogen").fetchall()
    return {name: pid for name, pid in rows}


def run(weeks_back: int) -> None:
    con = get_connection()
    geo_by_state = load_geo_lookup(con)
    pathogen_by_name = load_pathogen_lookup(con)

    since = date.today() - timedelta(weeks=weeks_back)
    print(f"Fetching {DATASET_URL} for week_end >= {since.isoformat()} ...")
    records = fetch_records(since)
    print(f"Fetched {len(records)} raw records.")

    rows_to_insert = []
    skipped_no_state = 0
    skipped_no_pathogen = 0
    unknown_pathogens: set[str] = set()

    for rec in records:
        state_name = rec.get("state_territory", "")
        state_abbr = STATE_NAME_TO_ABBR.get(state_name.lower())
        geo_id = geo_by_state.get(state_abbr) if state_abbr else None
        if geo_id is None:
            skipped_no_state += 1
            continue

        pathogen_target = rec.get("pathogen_target", "")
        canonical = PATHOGEN_MAP.get(pathogen_target)
        pathogen_id = pathogen_by_name.get(canonical) if canonical else None
        if pathogen_id is None:
            skipped_no_pathogen += 1
            unknown_pathogens.add(pathogen_target)
            continue

        wval_raw = rec.get("site_wval")
        if wval_raw in (None, ""):
            continue
        try:
            wval = float(wval_raw)
        except ValueError:
            continue

        week_end = datetime.strptime(rec["week_end"][:10], "%Y-%m-%d").date()
        week_start = week_end - timedelta(days=6)

        rows_to_insert.append((
            SOURCE_ID,
            "wastewater",
            geo_id,
            pathogen_id,
            week_start,
            week_end,
            "wval",
            wval,
            "activity_level_0_10",
            json.dumps(rec),
        ))

    if not rows_to_insert:
        print("No rows to insert -- check dataset availability / field names.")
        return

    con.executemany(
        """INSERT INTO fact_observation
           (source_id, domain, geo_id, pathogen_id, period_start, period_end,
            metric_name, metric_value, metric_unit, raw_payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows_to_insert,
    )
    print(f"Inserted {len(rows_to_insert)} rows into fact_observation.")
    print(f"Skipped {skipped_no_state} rows (unmapped state), "
          f"{skipped_no_pathogen} rows (unmapped pathogen).")
    if unknown_pathogens:
        print(f"Unknown pathogen_target values encountered: {unknown_pathogens}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=12,
                         help="How many weeks back to pull (default 12).")
    args = parser.parse_args()
    run(args.weeks)
