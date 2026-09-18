-- Biothreat Radar — unified data schema
--
-- Star schema: one long-format fact table (fact_observation) fed by four
-- heterogeneous domains (wastewater, syndromic, genomic, travel), joined
-- through three dimension tables. See dim_geo for how geographies at very
-- different native granularities (sampling site, airport, state, HHS
-- region, country) roll up to a common hierarchy.

-- ============================================================
-- Dimension: Geography (hierarchical, spans all 4 domains)
-- ============================================================
-- NOTE: no FOREIGN KEY constraints in this schema (see fact_observation).
-- parent_geo_id is a logical self-reference, enforced by the seed/ETL code,
-- not the database.
CREATE TABLE IF NOT EXISTS dim_geo (
    geo_id        BIGINT PRIMARY KEY,
    geo_type      VARCHAR NOT NULL,   -- 'wastewater_site' | 'airport' | 'county' | 'state' |
                                       -- 'hhs_region' | 'country' | 'who_region' | 'national' | 'global'
    geo_code      VARCHAR NOT NULL,   -- FIPS, IATA code, state abbrev, ISO-3166, HHS region #, etc.
    geo_name      VARCHAR NOT NULL,
    parent_geo_id BIGINT,             -- logical self-reference, see note above
    lat           DOUBLE,
    lon           DOUBLE,
    geojson_key   VARCHAR,            -- lookup key into data/geojson/ boundary files for the map
    UNIQUE(geo_type, geo_code)
);

-- ============================================================
-- Dimension: Pathogen / signal taxonomy
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_pathogen (
    pathogen_id    INTEGER PRIMARY KEY,
    canonical_name VARCHAR NOT NULL UNIQUE,  -- 'SARS-CoV-2', 'Influenza A', 'RSV', 'Mpox', 'Measles', ...
    category       VARCHAR                    -- 'respiratory' | 'enteric' | 'vaccine-preventable' | 'amr' | 'other'
);

-- ============================================================
-- Dimension: Source registry (provenance + access metadata)
-- Doubles as the data backing an /api/sources transparency endpoint.
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_source (
    source_id      INTEGER PRIMARY KEY,
    source_name    VARCHAR NOT NULL UNIQUE,  -- 'CDC NWSS', 'CDC NSSP ED Visits', 'Delphi FluView', ...
    domain         VARCHAR NOT NULL,         -- 'wastewater' | 'syndromic' | 'genomic' | 'travel'
    sponsor        VARCHAR,                  -- 'CDC' | 'Delphi (CMU)' | 'Nextstrain' | 'US DOT/BTS' | ...
    access_url     VARCHAR,
    access_model   VARCHAR,                  -- 'open_api' | 'open_scrape' | 'restricted'
    update_cadence VARCHAR,                  -- 'weekly' | 'monthly' | '15day_rolling' | 'event_driven'
    notes          VARCHAR
);

-- ============================================================
-- Fact: unified long-format observations across all domains
--
-- Deliberately NO FOREIGN KEY constraints to dim_source/dim_geo/dim_pathogen.
-- DuckDB implements both UPDATE and INSERT...ON CONFLICT DO UPDATE on a
-- FK-referenced parent row as an internal delete+reinsert, which is blocked
-- once any child row exists -- i.e. real FKs here would make dimension data
-- (source notes, geo names, pathogen taxonomy) permanently uneditable after
-- the first ETL run. Referential integrity is enforced by the seed/ETL code
-- instead (every writer looks up dimension IDs from the tables below before
-- inserting a fact row).
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS seq_observation_id START 1;

CREATE TABLE IF NOT EXISTS fact_observation (
    observation_id BIGINT PRIMARY KEY DEFAULT nextval('seq_observation_id'),
    source_id      INTEGER NOT NULL,          -- logical FK -> dim_source.source_id
    domain         VARCHAR NOT NULL,          -- denormalized copy of dim_source.domain, for fast filtering
    geo_id         BIGINT NOT NULL,           -- logical FK -> dim_geo.geo_id
    pathogen_id    INTEGER,                   -- logical FK -> dim_pathogen.pathogen_id; nullable (e.g. passenger counts aren't pathogen-specific)
    period_start   DATE NOT NULL,
    period_end     DATE NOT NULL,
    metric_name    VARCHAR NOT NULL,          -- 'ptc_15d', 'percent_ed_visits', 'variant_share', 'passenger_count', ...
    metric_value   DOUBLE,
    metric_unit    VARCHAR,                   -- 'percent' | 'proportion' | 'count' | 'percentile' | 'boolean'
    raw_payload    JSON,                      -- original source record, kept for traceability/debugging
    ingested_at    TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_fact_geo_period ON fact_observation(geo_id, period_start);
CREATE INDEX IF NOT EXISTS idx_fact_domain     ON fact_observation(domain);
CREATE INDEX IF NOT EXISTS idx_fact_pathogen   ON fact_observation(pathogen_id);
CREATE INDEX IF NOT EXISTS idx_fact_source     ON fact_observation(source_id);
