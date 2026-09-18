"""ETL: travel-based signals -> fact_observation.

Two sources (dim_source ids 12 and 13):

1. BTS International Passengers (xgub-n9bw) -- monthly T-100 passenger counts
   per US/foreign airport pair. Confirmed real but with a genuine ~9-month
   reporting lag (max data_dte 2025-12-01 as of this build) -- that's how
   T-100 carrier filings actually work, not staleness. Aggregated here to
   total inbound passengers per TGS airport per month (a covariate, not a
   health signal). Foreign-country breakdown skipped this pass -- would need
   a fg_apt -> country lookup we don't have yet.

2. WHO Disease Outbreak News (unofficial JSON API) -- confirmed current
   (latest entry 2026-09-10). No structured country/pathogen field -- both
   are parsed heuristically from the Title field (e.g. "Ebola disease caused
   by Bundibugyo virus - Democratic Republic of the Congo"). Multi-country
   titles produce one row per matched country; unmatched titles fall back to
   the 'global' geo row rather than being dropped. This is a best-effort
   proxy signal, documented as fragile in dim_source -- not a substitute for
   a real structured feed. raw_payload includes WHO's own Overview/
   Assessment/Epidemiology narrative fields (HTML-embedded) -- the actual
   substance an AI briefing needs, not just headlines.

Run: uv run python -m etl.travel [--weeks N]
"""

import argparse
import json
import re
from datetime import date, datetime, timedelta

import httpx

from db import get_connection

BTS_URL = "https://data.transportation.gov/resource/xgub-n9bw.json"
BTS_SOURCE_ID = 12
WHO_DON_URL = "https://www.who.int/api/news/diseaseoutbreaknews"
WHO_DON_SOURCE_ID = 13
PAGE_SIZE = 5000

TGS_AIRPORTS = ["LAX", "SFO", "JFK", "IAD", "EWR", "BOS", "SEA", "MIA", "ORD"]


# ---------------------------------------------------------------------------
# BTS International Passengers
# ---------------------------------------------------------------------------

def load_airport_lookup(con) -> dict[str, int]:
    rows = con.execute("SELECT geo_code, geo_id FROM dim_geo WHERE geo_type='airport'").fetchall()
    return {code: gid for code, gid in rows}


def run_bts(con, months_back: int, airport_geo: dict[str, int]) -> int:
    # BTS T-100 filings run ~9 months behind "today" -- anchor the lookback
    # window to the dataset's own max available date, not the current date,
    # or a "recent months" filter silently returns zero rows.
    max_date_resp = httpx.get(BTS_URL, params={"$select": "max(data_dte) as max_date"}, timeout=30.0)
    max_date_resp.raise_for_status()
    max_date_str = max_date_resp.json()[0]["max_date"][:10]
    latest_available = datetime.strptime(max_date_str, "%Y-%m-%d").date()
    since = latest_available - timedelta(days=months_back * 31)

    airport_list = ",".join(f"'{a}'" for a in TGS_AIRPORTS)
    print(f"[BTS] Latest available data_dte: {latest_available.isoformat()}. "
          f"Fetching usg_apt in ({airport_list}), data_dte >= {since.isoformat()} ...")

    records, offset = [], 0
    while True:
        resp = httpx.get(
            BTS_URL,
            params={
                "$limit": PAGE_SIZE,
                "$offset": offset,
                "$where": f"usg_apt in ({airport_list}) AND data_dte >= '{since.isoformat()}' AND type='Passengers'",
                "$order": "data_dte",
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
    print(f"[BTS] Fetched {len(records)} raw records.")

    # Aggregate to (airport, month) total across all foreign origins/carriers.
    totals: dict[tuple[str, date], float] = {}
    raw_by_key: dict[tuple[str, date], list[dict]] = {}
    for rec in records:
        apt = rec.get("usg_apt")
        if apt not in airport_geo:
            continue
        month = datetime.strptime(rec["data_dte"][:10], "%Y-%m-%d").date().replace(day=1)
        total = float(rec.get("total") or 0)
        key = (apt, month)
        totals[key] = totals.get(key, 0.0) + total
        raw_by_key.setdefault(key, []).append(rec)

    rows = []
    for (apt, month), total in totals.items():
        month_end = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        rows.append((
            BTS_SOURCE_ID, "travel", airport_geo[apt], None,
            month, month_end, "inbound_passengers", total, "count",
            json.dumps({"airport": apt, "month": month.isoformat(), "n_routes": len(raw_by_key[(apt, month)])}),
        ))

    if rows:
        con.executemany(
            """INSERT INTO fact_observation
               (source_id, domain, geo_id, pathogen_id, period_start, period_end,
                metric_name, metric_value, metric_unit, raw_payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    print(f"[BTS] Inserted {len(rows)} aggregated (airport, month) rows.")
    return len(rows)


# ---------------------------------------------------------------------------
# WHO Disease Outbreak News
# ---------------------------------------------------------------------------

def load_country_lookup(con) -> dict[str, int]:
    rows = con.execute("SELECT geo_name, geo_id FROM dim_geo WHERE geo_type='country'").fetchall()
    return {name.lower(): gid for name, gid in rows}


def load_pathogen_lookup(con) -> list[tuple[str, int]]:
    """Return (lowercase canonical_name, pathogen_id), longest names first so
    e.g. 'Influenza A' doesn't shadow a hypothetical more specific match."""
    rows = con.execute("SELECT canonical_name, pathogen_id FROM dim_pathogen").fetchall()
    return sorted(((n.lower(), pid) for n, pid in rows), key=lambda x: -len(x[0]))


# A few free-text aliases WHO DON titles use that don't exactly match our
# canonical pathogen names.
PATHOGEN_ALIASES = {
    "ebola": "Viral Hemorrhagic Fever (Ebola/Marburg)",
    "marburg": "Viral Hemorrhagic Fever (Ebola/Marburg)",
    "mpox": "Mpox",
    "monkeypox": "Mpox",
    "avian influenza": "Influenza A",
    "influenza": "Influenza A",
    "cholera": "Cholera",
    "measles": "Measles",
    "yellow fever": "Yellow Fever",
    "hantavirus": "Hantavirus",
    "nipah": "Nipah Virus",
    "poliovirus": "Poliovirus",
    "polio": "Poliovirus",
}


def match_pathogen(title: str, pathogen_by_name: dict[str, int]) -> int | None:
    title_lower = title.lower()
    for alias, canonical in PATHOGEN_ALIASES.items():
        if alias in title_lower:
            return pathogen_by_name.get(canonical.lower())
    return None


def match_countries(title: str, country_geo: dict[str, int]) -> list[int]:
    """Split a DON title on common separators and match each segment against
    known country names. Titles look like 'Disease - Country' or
    'Disease, Country1 & Country2'."""
    # Drop the leading disease name (before the first ' - ' or first comma).
    location_part = re.split(r"\s[-–]\s|,", title, maxsplit=1)
    tail = location_part[1] if len(location_part) > 1 else title
    segments = re.split(r"&|,", tail)

    matched = []
    for seg in segments:
        seg_clean = seg.strip().lower()
        if seg_clean in country_geo:
            matched.append(country_geo[seg_clean])
    return matched


def run_who_don(con, weeks_back: int, country_geo: dict[str, int],
                 pathogen_by_name: dict[str, int], global_geo_id: int | None) -> int:
    since = datetime.now() - timedelta(weeks=weeks_back)
    print(f"[WHO DON] Fetching {WHO_DON_URL} for entries since {since.date().isoformat()} ...")

    # Server enforces a hard $top limit of 100 (confirmed empirically -- not
    # documented). Page with $skip until a page comes back short or we've
    # gone past the requested window.
    records = []
    skip = 0
    while True:
        resp = httpx.get(
            WHO_DON_URL,
            params={
                "$orderby": "PublicationDateAndTime desc",
                "$top": 100,
                "$skip": skip,
                # Overview/Assessment/Epidemiology are WHO's own narrative
                # fields (HTML-embedded) -- the actual substance an AI
                # briefing needs. Originally only Id/Title/PublicationDate
                # were fetched, which left nothing but headlines to work with.
                "$select": "Id,Title,PublicationDate,Overview,Assessment,Epidemiology",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        page = resp.json().get("value", [])
        if not page:
            break
        records.extend(page)
        oldest_on_page = datetime.strptime(page[-1]["PublicationDate"][:19], "%Y-%m-%dT%H:%M:%S")
        skip += 100
        if oldest_on_page < since or len(page) < 100:
            break
    print(f"[WHO DON] Fetched {len(records)} raw records (unfiltered).")

    rows = []
    skipped_old = 0
    skipped_no_geo = 0
    for rec in records:
        pub_date = datetime.strptime(rec["PublicationDate"][:19], "%Y-%m-%dT%H:%M:%S")
        if pub_date < since:
            skipped_old += 1
            continue

        title = rec.get("Title") or ""
        geo_ids = match_countries(title, country_geo)
        if not geo_ids:
            if global_geo_id is None:
                skipped_no_geo += 1
                continue
            geo_ids = [global_geo_id]

        pathogen_id = match_pathogen(title, pathogen_by_name)
        day = pub_date.date()

        for geo_id in geo_ids:
            rows.append((
                WHO_DON_SOURCE_ID, "travel", geo_id, pathogen_id,
                day, day, "who_don_alert", 1.0, "boolean",
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
    print(f"[WHO DON] Inserted {len(rows)} rows (one per matched country). "
          f"Skipped {skipped_old} (outside window), {skipped_no_geo} (no geo match, no global fallback).")
    return len(rows)


def run(weeks_back: int) -> None:
    con = get_connection()
    airport_geo = load_airport_lookup(con)
    country_geo = load_country_lookup(con)
    pathogen_by_name = dict(load_pathogen_lookup(con))
    global_row = con.execute("SELECT geo_id FROM dim_geo WHERE geo_type='global'").fetchone()
    global_geo_id = global_row[0] if global_row else None

    n1 = run_bts(con, months_back=max(weeks_back // 4, 3), airport_geo=airport_geo)
    n2 = run_who_don(con, weeks_back=weeks_back, country_geo=country_geo,
                      pathogen_by_name=pathogen_by_name, global_geo_id=global_geo_id)
    print(f"Total travel rows inserted: {n1 + n2}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=26,
                         help="Lookback window for WHO DON; BTS uses weeks/4 as months (default 26).")
    args = parser.parse_args()
    run(args.weeks)
