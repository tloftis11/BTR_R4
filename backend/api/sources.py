"""Transparency endpoint: what data sources back this app, and how.

Reads directly from dim_source rather than a hardcoded list, so it always
reflects what's actually registered -- including sources we evaluated and
deliberately excluded (see seed/seed_sources.py for the full research trail).
"""

from fastapi import APIRouter

from db import get_connection

router = APIRouter()


@router.get("/api/sources")
def get_sources():
    con = get_connection()
    rows = con.execute(
        """SELECT source_name, domain, sponsor, access_url, access_model,
                  update_cadence, notes
           FROM dim_source
           ORDER BY domain, source_name"""
    ).fetchall()
    columns = ["name", "domain", "sponsor", "url", "access_model", "cadence", "notes"]
    return {"sources": [dict(zip(columns, row)) for row in rows]}


@router.get("/api/observations/summary")
def observations_summary():
    """Quick counts per domain -- useful for confirming ETL runs landed data."""
    con = get_connection()
    rows = con.execute(
        """SELECT domain, COUNT(*) AS n, MIN(period_end) AS earliest, MAX(period_end) AS latest
           FROM fact_observation
           GROUP BY domain
           ORDER BY domain"""
    ).fetchall()
    columns = ["domain", "observation_count", "earliest_period_end", "latest_period_end"]
    return {"domains": [dict(zip(columns, row)) for row in rows]}
