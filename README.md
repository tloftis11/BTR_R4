# Biothreat Radar (demo)

A real-data biosurveillance demo spanning four signal types — wastewater,
syndromic, genomic, and travel-based — built as a proof-of-concept for a
CDC biothreat radar program. Architecture pattern borrowed from an earlier
hotspot-detection app (ETL → unified store → composite scoring → map), but
every observation here is pulled from a real, live public data source —
no synthetic/seeded observational data.

## Data sources

Every source evaluated (used and excluded) is documented in
`backend/seed/seed_sources.py` and queryable live via `GET /api/sources`.

| Domain | Primary source | Access |
|---|---|---|
| Wastewater | CDC Wastewater Viral Activity Level | Open API |
| Syndromic | CDC NSSP ED Visits + Delphi FluView (ILINet) | Open API |
| Genomic | CDC Variant Proportions + Nextstrain | Open API |
| Travel | BTS International Passengers + WHO Disease Outbreak News | Open API (WHO endpoint unofficial) |

Travel is the weakest domain for clean API access — the two genuinely
health-relevant travel sources (CDC Traveler Genomic Surveillance, CDC
Travel Health Notices) are dashboard/HTML-only with no API, and are
documented but not yet integrated.

## Schema

Star schema in DuckDB: `dim_geo` (hierarchical — site/airport/county/state/
HHS region/country/WHO region, so a wastewater sampling site and a travel
country-pair can both roll up to a common geography), `dim_pathogen`
(canonical taxonomy), `dim_source` (provenance registry), and one long-format
`fact_observation` table. See `backend/schema.sql` for the full DDL and
rationale.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
cp .env.example .env          # add ANTHROPIC_API_KEY when needed

# Populate reference dimensions (static data, no API calls)
uv run python -m seed.seed_sources
uv run python -m seed.seed_pathogens
uv run python -m seed.seed_geo

# Pull real data (each hits a live public API)
uv run python -m etl.wastewater --weeks 12
uv run python -m etl.syndromic --weeks 12
uv run python -m etl.genomic --weeks 26
uv run python -m etl.travel --weeks 26

uv run uvicorn main:app --reload   # http://localhost:8000
```

## Status

- [x] Schema designed and validated
- [x] Wastewater ETL — CDC Wastewater Viral Activity Level (35,009 rows)
- [x] Syndromic ETL — NSSP ED Visit Trajectories + Delphi FluView (83,462 rows)
- [x] Genomic ETL — CDC Variant Proportions (1,491 rows); Nextstrain deferred
      (most builds checked were stale; would need phylogenetic tree parsing)
- [x] Travel ETL — BTS passenger volumes + WHO Disease Outbreak News (91 rows)
- [ ] Frontend map
- [ ] Composite scoring layer (deferred — HermesBoost integration TBD)

**120,053 real observations loaded** across all 4 domains as of 2026-09-18.
Several sources required correcting mid-build after the originally-researched
dataset turned out to be stale or a poor fit once actually queried — see
`backend/seed/seed_sources.py` for the full, honest trail (what was checked,
what changed, and why) rather than a static list of "sources used."
