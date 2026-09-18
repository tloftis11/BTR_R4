"""Map data endpoints.

The four domains report at genuinely different native geographies (state for
wastewater, county for syndromic, HHS-region for genomic, airport/country for
travel) -- there's no single query that treats them uniformly. Rather than
force a fake common granularity, this exposes what each domain can actually
support:

- /api/map/states: per-state latest SARS-CoV-2 signal from each of
  wastewater/syndromic/genomic (the one pathogen all three cover). Syndromic
  is a county average rolled up to state; genomic is the parent HHS region's
  value shared by all its member states -- both explicitly labeled as such
  in the response, not presented as if they were native state-level reads.
- /api/map/airports: latest BTS inbound passenger volume per TGS airport.
- /api/map/outbreak-alerts: recent WHO DON alerts by country, most recent first.
"""

from fastapi import APIRouter

from db import get_connection

router = APIRouter()

SARS_COV_2 = "SARS-CoV-2"


@router.get("/api/map/states")
def map_states():
    con = get_connection()

    # Wastewater: already state-level. Latest wval per state, this pathogen.
    wastewater = con.execute(
        """
        SELECT g.geo_name AS state, f.metric_value, f.period_end
        FROM fact_observation f
        JOIN dim_geo g ON f.geo_id = g.geo_id
        JOIN dim_pathogen p ON f.pathogen_id = p.pathogen_id
        WHERE f.domain = 'wastewater' AND p.canonical_name = ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY g.geo_code ORDER BY f.period_end DESC) = 1
        """,
        [SARS_COV_2],
    ).fetchall()

    # Syndromic: county-level NSSP rows, averaged up to their parent state,
    # using each county's own most recent period.
    syndromic = con.execute(
        """
        WITH latest_per_county AS (
            SELECT g.parent_geo_id AS state_geo_id, f.metric_value, f.period_end,
                   ROW_NUMBER() OVER (PARTITION BY f.geo_id ORDER BY f.period_end DESC) AS rn
            FROM fact_observation f
            JOIN dim_geo g ON f.geo_id = g.geo_id
            JOIN dim_pathogen p ON f.pathogen_id = p.pathogen_id
            WHERE f.domain = 'syndromic' AND f.metric_name = 'percent_ed_visits'
                  AND p.canonical_name = ? AND g.geo_type = 'county'
        )
        SELECT sg.geo_name AS state, AVG(l.metric_value) AS avg_value, MAX(l.period_end) AS period_end
        FROM latest_per_county l
        JOIN dim_geo sg ON l.state_geo_id = sg.geo_id
        WHERE l.rn = 1
        GROUP BY sg.geo_name
        """,
        [SARS_COV_2],
    ).fetchall()

    # Genomic: HHS-region level. Share applied to every member state of that region.
    genomic = con.execute(
        """
        WITH latest_per_region AS (
            SELECT g.geo_id AS region_geo_id, f.metric_value, f.period_end,
                   ROW_NUMBER() OVER (PARTITION BY g.geo_id ORDER BY f.period_end DESC) AS rn
            FROM fact_observation f
            JOIN dim_geo g ON f.geo_id = g.geo_id
            WHERE f.domain = 'genomic' AND g.geo_type = 'hhs_region'
                  AND f.metric_name LIKE 'variant_share:%'
        ),
        region_totals AS (
            -- sum of all variant shares for that region/period = ~1.0; we want
            -- the single dominant (highest-share) variant per region for the map
            SELECT region_geo_id, metric_value, period_end,
                   ROW_NUMBER() OVER (PARTITION BY region_geo_id ORDER BY metric_value DESC) AS share_rank
            FROM latest_per_region WHERE rn = 1
        )
        SELECT s.geo_name AS state, r.metric_value AS dominant_variant_share, r.period_end
        FROM region_totals r
        JOIN dim_geo s ON s.parent_geo_id = r.region_geo_id AND s.geo_type = 'state'
        WHERE r.share_rank = 1
        """
    ).fetchall()

    by_state: dict[str, dict] = {}
    for state, value, period_end in wastewater:
        by_state.setdefault(state, {})["wastewater"] = {
            "metric": "wval", "value": value, "period_end": str(period_end), "granularity": "state",
        }
    for state, value, period_end in syndromic:
        by_state.setdefault(state, {})["syndromic"] = {
            "metric": "percent_ed_visits", "value": value, "period_end": str(period_end),
            "granularity": "county_avg",
        }
    for state, value, period_end in genomic:
        by_state.setdefault(state, {})["genomic"] = {
            "metric": "dominant_variant_share", "value": value, "period_end": str(period_end),
            "granularity": "hhs_region_shared",
        }

    return {"pathogen": SARS_COV_2, "states": by_state}


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
        import json
        title = json.loads(raw_payload).get("Title") if raw_payload else None
        alerts.append({
            "country": country, "pathogen": pathogen,
            "date": str(alert_date), "title": title,
        })
    return {"alerts": alerts}
