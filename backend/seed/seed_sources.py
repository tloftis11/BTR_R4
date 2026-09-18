"""Seed dim_source: the registry of every real data source evaluated for this
project, including ones deliberately excluded. Kept even for excluded sources
so the provenance/transparency layer (/api/sources) can show what was
considered, not just what was integrated.

access_model values:
  open_api      - programmatic, no auth required (token optional for rate limits)
  open_scrape   - publicly viewable but no API; would require HTML/JS scraping
  restricted    - requires partner credentialing or a data use agreement
  discontinued  - was public, has been sunset
"""

from db import get_connection

SOURCES = [
    # id, name, domain, sponsor, access_url, access_model, update_cadence, notes
    (1, "CDC Wastewater Viral Activity Level", "wastewater", "CDC",
     "https://data.cdc.gov/resource/atcp-73re.json", "open_api", "weekly",
     "CORRECTED 2026-09-18: the previously-documented dataset (2ew6-ywp6, "
     "pre-computed ptc_15d/detect_prop_15d metrics) stopped receiving new data "
     "around Sept 2025 despite still responding to queries -- CDC migrated to "
     "per-pathogen datasets. atcp-73re is the verified-current replacement: "
     "weekly Wastewater Viral Activity Level (0-10 scale + category) for "
     "SARS-CoV-2/Influenza A/RSV, confirmed fresh through week_end 2026-09-12. "
     "Geography is state + county NAME (text), no FIPS -- ETL maps to state-level "
     "dim_geo; county name is kept in raw_payload for future enrichment. "
     "Also newly available as of this check: CDC now publishes a dedicated "
     "measles wastewater dataset (akvg-8vrb, raw PCR concentrations, not yet "
     "integrated) -- worth a follow-up ETL. "
     "DATA QUALITY NOTE (found during first real ETL run): site_wval is USUALLY "
     "0-10 but not bounded -- ~0.7% of Influenza A/RSV rows report values in the "
     "thousands (e.g. 46759) during real 'Very High' category spikes at "
     "low-baseline sites, confirmed across multiple source providers "
     "(CDC_Verily, State_Territory, WastewaterSCAN), not an ETL bug. Any "
     "visualization/scoring built on this field should use a log scale or "
     "percentile binning, not a naive linear 0-10 assumption."),
    (2, "WastewaterSCAN", "wastewater", "Stanford/Emory/Verily",
     "https://data.wastewaterscan.org", "open_scrape", "weekly",
     "Broadest pathogen panel (adds measles, TB, norovirus, antibiotic-resistance "
     "genes) but dashboard-only; CC BY-NC, bulk data requires emailing the team."),
    (3, "Biobot Analytics", "wastewater", "Biobot Analytics",
     "https://biobot.io", "discontinued", None,
     "Public pathogen dashboard wound down ~July 2026; Biobot now directs users "
     "to CDC NWSS. Current public work is substance-use monitoring, not pathogens."),

    (4, "CDC NSSP ED Visit Trajectories", "syndromic", "CDC",
     "https://data.cdc.gov/resource/rdmq-nq56.json", "open_api", "weekly",
     "CORRECTED 2026-09-18: originally documented as 7xva-uux8, but that "
     "dataset has NO unstratified total row -- every row is split by Sex, "
     "Age Group, or Race/Ethnicity, and it's national-only (no state/county). "
     "rdmq-nq56 is the actual best fit: county-level (real FIPS field) percent "
     "ED visits for COVID/Influenza/RSV, unstratified, plus a smoothed value "
     "and trend direction per pathogen. Confirmed fresh (week_end 2026-09-12)."),
    (5, "Delphi Epidata FluView (ILINet)", "syndromic", "Delphi (CMU) / CDC",
     "https://api.delphi.cmu.edu/epidata/fluview/", "open_api", "weekly",
     "Outpatient influenza-like-illness %, national/HHS-region/state, no auth "
     "required for public data."),
    (6, "NREVSS", "syndromic", "CDC",
     "https://www.cdc.gov/nrevss/php/dashboard/index.html", "open_scrape", "weekly",
     "Dashboard is live and current; the data.cdc.gov bulk export is stale "
     "(last updated Oct 2022) — treat as dashboard-only for a live pipeline."),
    (7, "NSSP ESSENCE / BioSense", "syndromic", "CDC",
     "https://www.cdc.gov/nssp/php/about/index.html", "restricted", "near_real_time",
     "Raw ED chief-complaint feed; requires public-health-agency credentialing. "
     "Not usable for an open demo."),

    (8, "CDC Variant Proportions", "genomic", "CDC",
     "https://data.cdc.gov/resource/jr58-6ysp.json", "open_api", "weekly",
     "SARS-CoV-2 only, national + 10 HHS regions, ~4-week reporting lag, "
     "confirmed actively updating."),
    (9, "Nextstrain", "genomic", "Nextstrain (Fred Hutch / Bedford Lab)",
     "https://data.nextstrain.org", "open_scrape", "varies_by_build",
     "CORRECTED 2026-09-18: freshness is NOT uniform across builds as earlier "
     "research suggested. Checked directly: ncov_open_global.json (SARS-CoV-2) "
     "stale since 2022-04-30; flu_seasonal_h3n2_ha_2y.json, measles.json, "
     "rsv_a_genome.json all stale since 2024. Only mpox_all-clades.json "
     "confirmed genuinely current (updated 2026-09-16). Also: the payload is a "
     "full Auspice phylogenetic tree (nested clades/branches), not tabular data "
     "-- deriving a trend metric requires tree traversal (counting tips per "
     "clade/region/time), a materially bigger ETL than any other source here. "
     "DEFERRED this pass; CDC Variant Proportions covers the SARS-CoV-2 variant-"
     "share need with a simple tabular pull. Revisit for mpox specifically, or "
     "if a dedicated tree-parsing pass is worth the investment later."),
    (10, "NCBI Virus / Datasets API", "genomic", "NIH/NLM",
     "https://api.ncbi.nlm.nih.gov/datasets/v2", "open_api", "continuous",
     "Raw sequence archive with geo/collection-date metadata; not a surveillance "
     "dashboard, but usable as backing data. NCBI Pathogen Detection (bacterial "
     "SNP clustering) is a related open, real-time system."),
    (11, "GISAID", "genomic", "GISAID",
     "https://gisaid.org", "restricted", None,
     "Requires identity verification + Database Access Agreement; broadest raw "
     "sequence pool but excluded from this project as not open."),

    (12, "BTS International Passengers", "travel", "US DOT / BTS",
     "https://data.transportation.gov/resource/xgub-n9bw.json", "open_api", "monthly",
     "Monthly T-100 nonstop international passenger counts by airport/country-pair. "
     "A covariate (import-risk proxy), not a health signal itself."),
    (13, "WHO Disease Outbreak News", "travel", "WHO",
     "https://www.who.int/api/news/diseaseoutbreaknews", "open_api", "event_driven",
     "Undocumented/unofficial JSON endpoint — treat as an integration risk despite "
     "being currently open. Proxy for 'active outbreak somewhere in the world.'"),
    (14, "CDC Traveler Genomic Surveillance (TGS)", "travel", "CDC / Ginkgo Bioworks",
     "https://www.cdc.gov/traveler-genomic-surveillance/php/data-vis/index.html",
     "open_scrape", "weekly",
     "Real pathogen detections (~30 pathogens) at 9 US airports from travelers "
     "arriving from 135+ countries. Best travel health signal, but HTML/JS "
     "dashboard only — no confirmed API."),
    (15, "CDC Travel Health Notices", "travel", "CDC",
     "https://wwwnc.cdc.gov/travel/notices", "open_scrape", "event_driven",
     "Outbreak-driven travel advisories by country/region, 4 severity levels. "
     "HTML only; an RSS feed is referenced but not yet verified."),
    (16, "GeoSentinel Surveillance Network", "travel", "CDC / ISTM",
     "https://www.geosentinel.org", "restricted", None,
     "Travel-clinic diagnosis network, 71 sites/29 countries; proprietary, "
     "permission-based access. Not usable without a data-sharing agreement."),
]


def seed_sources() -> None:
    """Upsert via explicit UPDATE-then-INSERT-if-missing, not ON CONFLICT --
    DuckDB implements ON CONFLICT DO UPDATE as delete+reinsert internally,
    which trips the fact_observation foreign key once real ETL data exists.
    A plain UPDATE never deletes the row, so it's FK-safe.
    """
    con = get_connection()
    existing_ids = {row[0] for row in con.execute("SELECT source_id FROM dim_source").fetchall()}

    updates, inserts = [], []
    for row in SOURCES:
        (updates if row[0] in existing_ids else inserts).append(row)

    if updates:
        con.executemany(
            """UPDATE dim_source SET
                   source_name = ?, domain = ?, sponsor = ?, access_url = ?,
                   access_model = ?, update_cadence = ?, notes = ?
               WHERE source_id = ?""",
            [(*row[1:], row[0]) for row in updates],
        )
    if inserts:
        con.executemany(
            """INSERT INTO dim_source
               (source_id, source_name, domain, sponsor, access_url, access_model,
                update_cadence, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            inserts,
        )
    print(f"dim_source: updated {len(updates)}, inserted {len(inserts)}.")


if __name__ == "__main__":
    seed_sources()
