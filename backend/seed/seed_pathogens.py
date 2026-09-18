"""Seed dim_pathogen: canonical pathogen/signal taxonomy spanning all four
domains. Source-specific names (e.g. NWSS's "sars-cov-2" vs NSSP's "COVID-19")
get mapped to these canonical_name values during ETL, so a query can compare
the same pathogen across domains.
"""

from db import get_connection

PATHOGENS = [
    # id, canonical_name, category
    (1, "SARS-CoV-2", "respiratory"),
    (2, "Influenza A", "respiratory"),
    (3, "Influenza B", "respiratory"),
    (4, "RSV", "respiratory"),
    (5, "Human Metapneumovirus", "respiratory"),
    (6, "Parainfluenza", "respiratory"),
    (7, "Rhinovirus/Enterovirus", "respiratory"),
    (8, "Enterovirus D68", "respiratory"),
    (9, "Human Coronavirus (seasonal)", "respiratory"),
    (10, "Adenovirus", "respiratory"),
    (11, "Tuberculosis", "respiratory"),
    (12, "Measles", "vaccine_preventable"),
    (13, "Poliovirus", "vaccine_preventable"),
    (14, "Mpox", "other"),
    (15, "Norovirus", "enteric"),
    (16, "Rotavirus", "enteric"),
    (17, "Hepatitis A", "enteric"),
    (18, "Cholera", "enteric"),
    (19, "Salmonella", "enteric"),
    (20, "E. coli/Shigella", "enteric"),
    (21, "Listeria", "enteric"),
    (22, "Campylobacter", "enteric"),
    (23, "West Nile Virus", "vector_borne"),
    (24, "Candida auris", "amr"),
    (25, "Carbapenem-resistant Enterobacteriaceae", "amr"),
    (26, "Viral Hemorrhagic Fever (Ebola/Marburg)", "other"),
    (27, "Hantavirus", "other"),
    (28, "Nipah Virus", "other"),
    (29, "Yellow Fever", "vector_borne"),
]


def seed_pathogens() -> None:
    """See seed_sources.seed_sources() for why this is UPDATE-then-INSERT
    rather than ON CONFLICT (DuckDB's ON CONFLICT DO UPDATE is FK-unsafe)."""
    con = get_connection()
    existing_ids = {row[0] for row in con.execute("SELECT pathogen_id FROM dim_pathogen").fetchall()}

    updates = [row for row in PATHOGENS if row[0] in existing_ids]
    inserts = [row for row in PATHOGENS if row[0] not in existing_ids]

    if updates:
        con.executemany(
            "UPDATE dim_pathogen SET canonical_name = ?, category = ? WHERE pathogen_id = ?",
            [(row[1], row[2], row[0]) for row in updates],
        )
    if inserts:
        con.executemany(
            "INSERT INTO dim_pathogen (pathogen_id, canonical_name, category) VALUES (?, ?, ?)",
            inserts,
        )
    print(f"dim_pathogen: updated {len(updates)}, inserted {len(inserts)}.")


if __name__ == "__main__":
    seed_pathogens()
