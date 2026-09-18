"""Map data endpoints.

The four domains report at genuinely different native geographies (state for
wastewater, county for syndromic, HHS-region for genomic, airport/country for
travel) -- there's no single query that treats them uniformly. This module
also does the work of turning raw metric values into things a reader can
actually interpret -- CDC already computes human-readable category labels
and trend directions for wastewater/syndromic, and the genomic data names
specific variants, but none of that was previously surfaced (see
build_states_payload's docstring for the full rationale).

- /api/map/states: build_states_payload() output, keyed by state name to
  match the frontend's GeoJSON join. All 3 tracked pathogens (SARS-CoV-2,
  Influenza A, RSV) are included for wastewater/syndromic in one response --
  not filtered to one at a time -- so the map, the state pullout panel, and
  the AI endpoints all read from the same structure.
- /api/map/airports: latest BTS inbound passenger volume per TGS airport.
- /api/map/outbreak-alerts: recent WHO DON alerts by country, with a real
  excerpt from WHO's own Overview/Assessment content, not just a title.
"""

import json
import re
from collections import Counter, defaultdict

from fastapi import APIRouter

from db import get_connection

router = APIRouter()

PATHOGENS = ["SARS-CoV-2", "Influenza A", "RSV"]

# CDC's own category labels -> a fixed ordinal, for map coloring on a scale
# that means the same thing every week (not relative to whatever's loaded).
WASTEWATER_CATEGORY_ORDINAL = {
    "Very Low": 0, "Low": 1, "Moderate": 2, "High": 3, "Very High": 4,
}

SYNDROMIC_TREND_FIELD = {
    "SARS-CoV-2": "ed_trends_covid",
    "Influenza A": "ed_trends_influenza",
    "RSV": "ed_trends_rsv",
}


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _wastewater_data(con) -> dict[str, dict[str, dict]]:
    """state -> pathogen -> {category_distribution, site_count, trend, period_end}.

    Queries every reporting site per state/pathogen/period (not one arbitrary
    site -- the previous version silently dropped every site but one via
    ROW_NUMBER()=1 in a multi-site state). Trend compares the average numeric
    wval at the latest period against the earliest period in the loaded
    window; category_distribution is CDC's own site_wval_category label,
    counted across sites at the latest period.
    """
    rows = con.execute(
        """
        SELECT g.geo_name AS state, p.canonical_name AS pathogen,
               f.period_end, f.metric_value, f.raw_payload
        FROM fact_observation f
        JOIN dim_geo g ON f.geo_id = g.geo_id
        JOIN dim_pathogen p ON f.pathogen_id = p.pathogen_id
        WHERE f.domain = 'wastewater'
        """
    ).fetchall()

    # state -> pathogen -> period_end -> [(metric_value, category), ...]
    data: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for state, pathogen, period_end, metric_value, raw_payload in rows:
        category = None
        if raw_payload:
            category = json.loads(raw_payload).get("site_wval_category")
        data[state][pathogen][period_end].append((metric_value, category))

    result: dict = defaultdict(dict)
    for state, pathogens in data.items():
        for pathogen, periods in pathogens.items():
            sorted_periods = sorted(periods.keys())
            latest_period = sorted_periods[-1]
            earliest_period = sorted_periods[0]
            latest_readings = periods[latest_period]
            earliest_readings = periods[earliest_period]

            category_distribution: dict[str, int] = {}
            for _, cat in latest_readings:
                if cat:
                    category_distribution[cat] = category_distribution.get(cat, 0) + 1

            if earliest_period == latest_period:
                trend = "stable"
            else:
                latest_avg = sum(v for v, _ in latest_readings) / len(latest_readings)
                earliest_avg = sum(v for v, _ in earliest_readings) / len(earliest_readings)
                baseline = max(abs(earliest_avg), 0.5)  # avoid noisy % swings near zero
                rel_change = (latest_avg - earliest_avg) / baseline
                trend = "rising" if rel_change > 0.15 else "falling" if rel_change < -0.15 else "stable"

            result[state][pathogen] = {
                "category_distribution": category_distribution,
                "site_count": len(latest_readings),
                "trend": trend,
                "period_end": str(latest_period),
            }
    return result


def _syndromic_data(con) -> dict[str, dict[str, dict]]:
    """state -> pathogen -> {percent_ed_visits, trend, period_end}.

    trend is CDC's own ed_trends_{pathogen} label from NSSP's trajectory
    dataset (Increasing/Decreasing/No Change), taken as the mode across
    counties for the state-level rollup -- not computed by us.
    """
    rows = con.execute(
        """
        WITH latest_per_county AS (
            SELECT g.geo_id AS county_geo_id, g.parent_geo_id AS state_geo_id,
                   p.canonical_name AS pathogen, f.metric_value, f.period_end, f.raw_payload,
                   ROW_NUMBER() OVER (
                       PARTITION BY f.geo_id, p.canonical_name ORDER BY f.period_end DESC
                   ) AS rn
            FROM fact_observation f
            JOIN dim_geo g ON f.geo_id = g.geo_id
            JOIN dim_pathogen p ON f.pathogen_id = p.pathogen_id
            WHERE f.domain = 'syndromic' AND f.metric_name = 'percent_ed_visits'
                  AND g.geo_type = 'county'
        )
        SELECT sg.geo_name AS state, l.pathogen, l.metric_value, l.period_end, l.raw_payload
        FROM latest_per_county l
        JOIN dim_geo sg ON l.state_geo_id = sg.geo_id
        WHERE l.rn = 1
        """
    ).fetchall()

    grouped: dict = defaultdict(list)
    for state, pathogen, value, period_end, raw_payload in rows:
        grouped[(state, pathogen)].append((value, period_end, raw_payload))

    result: dict = defaultdict(dict)
    for (state, pathogen), readings in grouped.items():
        values = [v for v, _, _ in readings]
        period_end = max(pe for _, pe, _ in readings)

        trend_field = SYNDROMIC_TREND_FIELD.get(pathogen)
        trends = []
        if trend_field:
            for _, _, raw_payload in readings:
                if raw_payload:
                    t = json.loads(raw_payload).get(trend_field)
                    if t:
                        trends.append(t)
        trend_label = Counter(trends).most_common(1)[0][0] if trends else None

        result[state][pathogen] = {
            "percent_ed_visits": round(sum(values) / len(values), 3),
            "trend": trend_label,
            "period_end": str(period_end),
        }
    return result


def _genomic_data(con) -> dict[str, dict]:
    """state -> {current_leader, fastest_growing, period_end}.

    SARS-CoV-2 only -- CDC's Variant Proportions source doesn't track other
    pathogens' lineages at all (a genuine source limitation, not a choice
    made here). current_leader is the highest-share variant at the latest
    period; fastest_growing compares against the prior distinct period and
    is null if there's only one period or nothing is gaining share.
    """
    rows = con.execute(
        """
        SELECT g.geo_id AS region_geo_id, f.metric_name, f.metric_value, f.period_end
        FROM fact_observation f
        JOIN dim_geo g ON f.geo_id = g.geo_id
        WHERE f.domain = 'genomic' AND g.geo_type = 'hhs_region'
              AND f.metric_name LIKE 'variant_share:%'
        """
    ).fetchall()

    # region_geo_id -> period_end -> variant -> share
    by_region: dict = defaultdict(lambda: defaultdict(dict))
    for region_geo_id, metric_name, metric_value, period_end in rows:
        variant = metric_name.split(":", 1)[1]
        by_region[region_geo_id][period_end][variant] = metric_value

    region_results: dict[int, dict] = {}
    for region_geo_id, periods in by_region.items():
        sorted_periods = sorted(periods.keys())
        latest_period = sorted_periods[-1]
        latest_shares = periods[latest_period]
        leader_variant = max(latest_shares, key=latest_shares.get)

        fastest_growing = None
        if len(sorted_periods) >= 2:
            prev_shares = periods[sorted_periods[-2]]
            deltas = {v: share - prev_shares.get(v, 0) for v, share in latest_shares.items()}
            fg_variant = max(deltas, key=deltas.get) if deltas else None
            if fg_variant and deltas[fg_variant] > 0:
                fastest_growing = {
                    "variant": fg_variant,
                    "share": round(latest_shares[fg_variant], 4),
                    "change": round(deltas[fg_variant], 4),
                }

        region_results[region_geo_id] = {
            "current_leader": {"variant": leader_variant, "share": round(latest_shares[leader_variant], 4)},
            "fastest_growing": fastest_growing,
            "period_end": str(latest_period),
        }

    state_rows = con.execute(
        "SELECT geo_name, parent_geo_id FROM dim_geo WHERE geo_type = 'state'"
    ).fetchall()
    return {
        state_name: region_results[parent_id]
        for state_name, parent_id in state_rows
        if parent_id in region_results
    }


def build_states_payload(con) -> dict:
    """The single source of truth for per-state signal data -- consumed by
    /api/map/states, the state pullout panel, and both AI endpoints (Part 3).
    All 3 pathogens are always included for wastewater/syndromic; genomic has
    no pathogen dimension (SARS-CoV-2 only).
    """
    wastewater = _wastewater_data(con)
    syndromic = _syndromic_data(con)
    genomic = _genomic_data(con)

    all_states = set(wastewater) | set(syndromic) | set(genomic)
    return {
        state: {
            "wastewater": wastewater.get(state, {}),
            "syndromic": syndromic.get(state, {}),
            "genomic": genomic.get(state),
        }
        for state in all_states
    }


@router.get("/api/map/states")
def map_states():
    con = get_connection()
    return {"pathogens": PATHOGENS, "states": build_states_payload(con)}


@router.get("/api/map/airports")
def map_airports():
    con = get_connection()
    rows = con.execute(
        """
        WITH latest AS (
            SELECT g.geo_code, g.geo_name, g.lat, g.lon, f.metric_value, f.period_start,
                   ROW_NUMBER() OVER (PARTITION BY g.geo_id ORDER BY f.period_start DESC) AS rn
            FROM fact_observation f
            JOIN dim_geo g ON f.geo_id = g.geo_id
            WHERE f.domain = 'travel' AND f.metric_name = 'inbound_passengers'
        )
        SELECT geo_code, geo_name, lat, lon, metric_value, period_start
        FROM latest WHERE rn = 1
        """
    ).fetchall()
    columns = ["iata", "name", "lat", "lon", "inbound_passengers", "period_start"]
    return {"airports": [dict(zip(columns, r)) for r in rows]}


@router.get("/api/map/outbreak-alerts")
def map_outbreak_alerts(limit: int = 20):
    con = get_connection()
    rows = con.execute(
        """
        SELECT g.geo_name AS country, p.canonical_name AS pathogen,
               f.period_start AS alert_date, f.raw_payload
        FROM fact_observation f
        JOIN dim_geo g ON f.geo_id = g.geo_id
        LEFT JOIN dim_pathogen p ON f.pathogen_id = p.pathogen_id
        WHERE f.domain = 'travel' AND f.metric_name = 'who_don_alert'
        ORDER BY f.period_start DESC
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    alerts = []
    for country, pathogen, alert_date, raw_payload in rows:
        rec = json.loads(raw_payload) if raw_payload else {}
        overview = _strip_html(rec.get("Overview"))
        excerpt = (overview[:280] + "...") if len(overview) > 280 else overview
        alerts.append({
            "country": country,
            "pathogen": pathogen,
            "date": str(alert_date),
            "title": rec.get("Title"),
            "excerpt": excerpt or None,
        })
    return {"alerts": alerts}
