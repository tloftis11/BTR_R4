"""ETL: CDC SARS-CoV-2 Variant Proportions -> fact_observation.

Source: https://data.cdc.gov/resource/jr58-6ysp.json (dim_source id=8)
National + 10 HHS regions, weekly-ish (4-week rolling windows), share of
each circulating lineage. Verified current 2026-09-18 (week_ending 2026-08-01,
creation_date 2026-08-28 -- the ~4-week lag is expected/documented).

Nextstrain was evaluated and deferred this pass -- see seed/seed_sources.py
for why (stale builds + phylogenetic tree parsing is out of scope for now).

Each variant's share becomes its own metric_name (e.g. "variant_share:LF.7.9")
since there's no separate variant dimension table -- keeps this additive if a
dim_variant table is ever worth adding later.

Run: uv run python -m etl.genomic [--weeks N]
"""

import argparse
import json
from datetime import date, datetime, timedelta

import httpx

from db import get_connection

DATASET_URL = "https://data.cdc.gov/resource/jr58-6ysp.json"
SOURCE_ID = 8
PAGE_SIZE = 5000
SARS_COV_2_CANONICAL = "SARS-CoV-2"


def load_geo_lookup(con) -> dict[str, int]:
    """geo_code ('USA' -> national US, '1'-'10' -> HHS regions) -> geo_id."""
    lookup = {}
    national = con.execute(
        "SELECT geo_id FROM dim_geo WHERE geo_type='national' AND geo_code='US'"
    ).fetchone()
    if national:
        lookup["USA"] = national[0]
    for code, gid in con.execute(
        "SELECT geo_code, geo_id FROM dim_geo WHERE geo_type='hhs_region'"
    ).fetchall():
        lookup[code] = gid
    return lookup


def fetch_records(since: date) -> list[dict]:
    records, offset = [], 0
    while True:
        resp = httpx.get(
            DATASET_URL,
            params={
                "$limit": PAGE_SIZE,
                "$offset": offset,
                "$where": f"week_ending >= '{since.isoformat()}'",
                "$order": "week_ending",
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


def run(weeks_back: int) -> None:
    con = get_connection()
    geo_by_code = load_geo_lookup(con)
    pathogen_id = con.execute(
        "SELECT pathogen_id FROM dim_pathogen WHERE canonical_name = ?",
        [SARS_COV_2_CANONICAL],
    ).fetchone()[0]

    since = date.today() - timedelta(weeks=weeks_back)
    print(f"Fetching {DATASET_URL} for week_ending >= {since.isoformat()} ...")
    records = fetch_records(since)
    print(f"Fetched {len(records)} raw records.")

    rows = []
    skipped_no_geo = 0
    for rec in records:
        geo_id = geo_by_code.get(rec.get("usa_or_hhsregion"))
        if geo_id is None:
            skipped_no_geo += 1
            continue

        share = rec.get("share")
        variant = rec.get("variant")
        if share is None or not variant:
            continue

        week_end = datetime.strptime(rec["week_ending"][:10], "%Y-%m-%d").date()
        week_start = week_end - timedelta(days=6)

        rows.append((
            SOURCE_ID, "genomic", geo_id, pathogen_id,
            week_start, week_end, f"variant_share:{variant}", float(share), "proportion",
            json.dumps(rec),
        ))

    if rows:
        con.executemany(
            """INSERT INTO fact_observation
               (source_id, domain, geo_id, pathogen_id, period_start, period_end,
                metric_name, metric_value, metric_unit, raw_payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    print(f"Inserted {len(rows)} rows. Skipped {skipped_no_geo} (unmapped geography).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=26,
                         help="Lookback window (default 26 -- variant data is sparse/quarterly-ish per region).")
    args = parser.parse_args()
    run(args.weeks)
