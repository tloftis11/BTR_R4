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

uv run uvicorn main:app --reload   # http://localhost:8000
```

## Status

- [x] Schema designed and validated
- [x] Wastewater ETL (CDC Wastewater Viral Activity Level)
- [ ] Syndromic ETL (NSSP ED Visits + Delphi FluView)
- [ ] Genomic ETL (CDC Variant Proportions + Nextstrain)
- [ ] Travel ETL (BTS passenger volumes + WHO DON)
- [ ] Frontend map
- [ ] Composite scoring layer (deferred — HermesBoost integration TBD)
