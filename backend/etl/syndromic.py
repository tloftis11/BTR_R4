"""ETL: syndromic surveillance -> fact_observation.

Two sources (dim_source ids 4 and 5):

1. CDC NSSP ED Visit Trajectories (rdmq-nq56) -- county-level (real FIPS),
   unstratified percent ED visits for COVID/Influenza/RSV. Verified current
   2026-09-18 (week_end 2026-09-12). NOTE: the originally-researched dataset
   (7xva-uux8) turned out to have no unstratified total row and no county/state
   breakdown -- see seed/seed_sources.py for the correction.

2. Delphi Epidata FluView / ILINet -- national + 10 HHS regions, weighted %
   ILI (wili). Verified current 2026-09-18 (epiweek 202635 / release 2026-09-11).

Run: uv run python -m etl.syndromic [--weeks N]
"""

import argparse
import json
from datetime import date, datetime, timedelta

import httpx

from db import get_connection
from seed.seed_geo import get_or_create_county

NSSP_URL = "https://data.cdc.gov/resource/rdmq-nq56.json"
NSSP_SOURCE_ID = 4
FLUVIEW_URL = "https://api.delphi.cmu.edu/epidata/fluview/"
FLUVIEW_SOURCE_ID = 5
PAGE_SIZE = 5000

# NSSP pathogen suffixes -> dim_pathogen.canonical_name
NSSP_PATHOGENS = {
    "covid": "SARS-CoV-2",
    "influenza": "Influenza A",   # NSSP's "Influenza" bucket isn't A/B split; mapped to Influenza A as the closest canonical bucket
    "rsv": "RSV",
}

FLUVIEW_REGIONS = ["nat"] + [f"hhs{i}" for i in range(1, 11)]


def load_pathogen_lookup(con) -> dict[str, int]:
    rows = con.execute("SELECT canonical_name, pathogen_id FROM dim_pathogen").fetchall()
    return {name: pid for name, pid in rows}


def load_geo_lookup(con) -> dict[str, int]:
    """geo_type:geo_code -> geo_id, for national/hhs_region/state rows."""
    rows = con.execute(
        "SELECT geo_type, geo_code, geo_id FROM dim_geo WHERE geo_type IN ('national','hhs_region','state')"
    ).fetchall()
    return {f"{t}:{c}": gid for t, c, gid in rows}


def epiweek_to_dates(epiweek: int) -> tuple[date, date]:
    """CDC epiweek (YYYYWW) -> (week_start, week_end), ISO-ish Sunday-Saturday week."""
    year, week = divmod(epiweek, 100)
    # epiweeks are CDC MMWR weeks (Sun-Sat); approximate via ISO week then shift to Sunday start.
    jan4 = date(year, 1, 4)
    week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
    week_start = week1_monday + timedelta(weeks=week - 1) - timedelta(days=1)  # shift Mon->Sun
    return week_start, week_start + timedelta(days=6)


def run_nssp(con, weeks_back: int, pathogen_by_name: dict[str, int]) -> int:
    since = date.today() - timedelta(weeks=weeks_back)
    print(f"[NSSP] Fetching {NSSP_URL} for week_end >= {since.isoformat()} ...")

    records, offset = [], 0
    while True:
        resp = httpx.get(
            NSSP_URL,
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
    print(f"[NSSP] Fetched {len(records)} raw records.")

    rows = []
    skipped_no_fips = 0
    for rec in records:
        fips = rec.get("fips")
        if not fips:
            skipped_no_fips += 1
            continue
        geo_id = get_or_create_county(con, fips, rec.get("county", ""))

        week_end = datetime.strptime(rec["week_end"][:10], "%Y-%m-%d").date()
        week_start = week_end - timedelta(days=6)

        for suffix, canonical in NSSP_PATHOGENS.items():
            raw_val = rec.get(f"percent_visits_{suffix}")
            if raw_val in (None, ""):
                continue
            try:
                val = float(raw_val)
            except ValueError:
                continue
            pathogen_id = pathogen_by_name.get(canonical)
            if pathogen_id is None:
                continue
            rows.append((
                NSSP_SOURCE_ID, "syndromic", geo_id, pathogen_id,
                week_start, week_end, "percent_ed_visits", val, "percent",
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
    print(f"[NSSP] Inserted {len(rows)} rows. Skipped {skipped_no_fips} (no FIPS).")
    return len(rows)


def run_fluview(con, weeks_back: int, pathogen_by_name: dict[str, int],
                 geo_by_key: dict[str, int]) -> int:
    end_week = date.today()
    start_week = end_week - timedelta(weeks=weeks_back)
    sy, sw, _ = start_week.isocalendar()
    ey, ew, _ = end_week.isocalendar()
    epiweek_range = f"{sy}{sw:02d}-{ey}{ew:02d}"

    print(f"[FluView] Fetching {FLUVIEW_URL} for regions={FLUVIEW_REGIONS}, epiweeks={epiweek_range} ...")
    resp = httpx.get(
        FLUVIEW_URL,
        params={"regions": ",".join(FLUVIEW_REGIONS), "epiweeks": epiweek_range},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    records = data.get("epidata", [])
    print(f"[FluView] Fetched {len(records)} raw records (result={data.get('result')}).")

    influenza_a_id = pathogen_by_name.get("Influenza A")
    rows = []
    skipped_no_geo = 0
    for rec in records:
        region = rec["region"]
        geo_key = "national:US" if region == "nat" else f"hhs_region:{region.replace('hhs', '')}"
        geo_id = geo_by_key.get(geo_key)
        if geo_id is None:
            skipped_no_geo += 1
            continue

        wili = rec.get("wili")
        if wili is None:
            continue
        week_start, week_end = epiweek_to_dates(rec["epiweek"])
        rows.append((
            FLUVIEW_SOURCE_ID, "syndromic", geo_id, influenza_a_id,
            week_start, week_end, "ili_weighted_pct", float(wili), "percent",
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
    print(f"[FluView] Inserted {len(rows)} rows. Skipped {skipped_no_geo} (unmapped region).")
    return len(rows)


def run(weeks_back: int) -> None:
    con = get_connection()
    pathogen_by_name = load_pathogen_lookup(con)
    geo_by_key = load_geo_lookup(con)
    # add "national:US" alias for fluview's 'nat' region
    national_row = con.execute(
        "SELECT geo_id FROM dim_geo WHERE geo_type='national' AND geo_code='US'"
    ).fetchone()
    if national_row:
        geo_by_key["national:US"] = national_row[0]

    n1 = run_nssp(con, weeks_back, pathogen_by_name)
    n2 = run_fluview(con, weeks_back, pathogen_by_name, geo_by_key)
    print(f"Total syndromic rows inserted: {n1 + n2}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=12)
    args = parser.parse_args()
    run(args.weeks)
