"""Seed dim_geo: the geographic hierarchy crosswalk spanning all 4 domains.

Populates national -> HHS region -> state (all static, well-known reference
data, no API needed) plus the 9 CDC Traveler Genomic Surveillance airports and
a starter WHO-region -> country crosswalk for travel/outbreak signals.

Counties (3000+) are NOT hand-seeded here -- the wastewater ETL inserts a
county row on first encounter (state is derivable from the FIPS code's first
2 digits, looked up against the state rows this script creates).
"""

from db import get_connection

# CDC's 10 HHS regions -> member states/territories (fixed structure)
HHS_REGIONS = {
    1: ("HHS Region 1", ["CT", "ME", "MA", "NH", "RI", "VT"]),
    2: ("HHS Region 2", ["NJ", "NY", "PR", "VI"]),
    3: ("HHS Region 3", ["DE", "DC", "MD", "PA", "VA", "WV"]),
    4: ("HHS Region 4", ["AL", "FL", "GA", "KY", "MS", "NC", "SC", "TN"]),
    5: ("HHS Region 5", ["IL", "IN", "MI", "MN", "OH", "WI"]),
    6: ("HHS Region 6", ["AR", "LA", "NM", "OK", "TX"]),
    7: ("HHS Region 7", ["IA", "KS", "MO", "NE"]),
    8: ("HHS Region 8", ["CO", "MT", "ND", "SD", "UT", "WY"]),
    9: ("HHS Region 9", ["AZ", "CA", "HI", "NV", "AS", "GU", "MP"]),
    10: ("HHS Region 10", ["AK", "ID", "OR", "WA"]),
}

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "VI": "U.S. Virgin Islands", "AS": "American Samoa",
    "GU": "Guam", "MP": "Northern Mariana Islands",
}

# The 9 CDC Traveler Genomic Surveillance airports -> (name, state, lat, lon)
TGS_AIRPORTS = {
    "LAX": ("Los Angeles Intl", "CA", 33.9416, -118.4085),
    "SFO": ("San Francisco Intl", "CA", 37.6213, -122.3790),
    "JFK": ("John F. Kennedy Intl", "NY", 40.6413, -73.7781),
    "IAD": ("Washington Dulles Intl", "VA", 38.9531, -77.4565),
    "EWR": ("Newark Liberty Intl", "NJ", 40.6895, -74.1745),
    "BOS": ("Boston Logan Intl", "MA", 42.3656, -71.0096),
    "SEA": ("Seattle-Tacoma Intl", "WA", 47.4502, -122.3088),
    "MIA": ("Miami Intl", "FL", 25.7959, -80.2870),
    "ORD": ("Chicago O'Hare Intl", "IL", 41.9742, -87.9073),
}

WHO_REGIONS = {
    "AFRO": "WHO African Region",
    "AMRO": "WHO Region of the Americas",
    "SEARO": "WHO South-East Asia Region",
    "EURO": "WHO European Region",
    "EMRO": "WHO Eastern Mediterranean Region",
    "WPRO": "WHO Western Pacific Region",
}

# Starter set of countries relevant to outbreak/travel signals (ISO-3166 alpha-2).
# Not exhaustive -- extend as WHO DON / Travel Health Notices ETL encounters new ones.
COUNTRIES = {
    "CD": ("Democratic Republic of the Congo", "AFRO"),
    "NG": ("Nigeria", "AFRO"),
    "UG": ("Uganda", "AFRO"),
    "ZA": ("South Africa", "AFRO"),
    "IN": ("India", "SEARO"),
    "ID": ("Indonesia", "SEARO"),
    "BD": ("Bangladesh", "SEARO"),
    "CN": ("China", "WPRO"),
    "PH": ("Philippines", "WPRO"),
    "VN": ("Vietnam", "WPRO"),
    "GB": ("United Kingdom", "EURO"),
    "FR": ("France", "EURO"),
    "DE": ("Germany", "EURO"),
    "MX": ("Mexico", "AMRO"),
    "BR": ("Brazil", "AMRO"),
    "CA": ("Canada", "AMRO"),
    "SA": ("Saudi Arabia", "EMRO"),
    "EG": ("Egypt", "EMRO"),
    "PK": ("Pakistan", "EMRO"),
}


def seed_geo() -> None:
    con = get_connection()
    rows: list[tuple] = []
    next_id = 1

    def add(geo_type, geo_code, geo_name, parent_id=None, lat=None, lon=None, geojson_key=None):
        nonlocal next_id
        gid = next_id
        next_id += 1
        rows.append((gid, geo_type, geo_code, geo_name, parent_id, lat, lon, geojson_key))
        return gid

    national_id = add("national", "US", "United States")
    global_id = add("global", "GLOBAL", "Global")

    hhs_region_ids = {
        region_num: add("hhs_region", str(region_num), region_name, national_id)
        for region_num, (region_name, _states) in HHS_REGIONS.items()
    }

    state_ids: dict[str, int] = {}
    for region_num, (_name, states) in HHS_REGIONS.items():
        for state_code in states:
            state_ids[state_code] = add(
                "state", state_code, STATE_NAMES.get(state_code, state_code),
                hhs_region_ids[region_num],
            )

    for iata, (airport_name, state_code, lat, lon) in TGS_AIRPORTS.items():
        add("airport", iata, airport_name, state_ids.get(state_code), lat, lon)

    who_region_ids = {code: add("who_region", code, name, global_id)
                       for code, name in WHO_REGIONS.items()}

    for iso2, (country_name, who_code) in COUNTRIES.items():
        add("country", iso2, country_name, who_region_ids[who_code])

    # UPDATE-then-INSERT, not ON CONFLICT -- see seed_sources.seed_sources()
    # for why (DuckDB's ON CONFLICT DO UPDATE is FK-unsafe against fact_observation).
    existing_ids = {r[0] for r in con.execute("SELECT geo_id FROM dim_geo").fetchall()}
    updates = [r for r in rows if r[0] in existing_ids]
    inserts = [r for r in rows if r[0] not in existing_ids]

    if updates:
        con.executemany(
            """UPDATE dim_geo SET geo_type = ?, geo_code = ?, geo_name = ?,
                   parent_geo_id = ?, lat = ?, lon = ?, geojson_key = ?
               WHERE geo_id = ?""",
            [(*r[1:], r[0]) for r in updates],
        )
    if inserts:
        con.executemany(
            """INSERT INTO dim_geo
               (geo_id, geo_type, geo_code, geo_name, parent_geo_id, lat, lon, geojson_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            inserts,
        )
    print(
        f"Seeded {len(rows)} rows into dim_geo "
        f"(1 national, 1 global, {len(HHS_REGIONS)} HHS regions, "
        f"{len(state_ids)} states/territories, {len(TGS_AIRPORTS)} airports, "
        f"{len(WHO_REGIONS)} WHO regions, {len(COUNTRIES)} countries)."
    )


def get_or_create_county(con, fips: str, county_name: str) -> int:
    """Look up a county geo_id, inserting it (parented to its state) on first
    encounter. Used by ETL scripts -- counties aren't pre-seeded (3000+ of them).
    """
    existing = con.execute(
        "SELECT geo_id FROM dim_geo WHERE geo_type = 'county' AND geo_code = ?", [fips]
    ).fetchone()
    if existing:
        return existing[0]

    state_fips_to_abbr = {
        "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
        "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
        "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
        "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
        "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
        "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
        "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
        "55": "WI", "56": "WY", "72": "PR", "78": "VI",
    }
    state_abbr = state_fips_to_abbr.get(fips[:2])
    parent = con.execute(
        "SELECT geo_id FROM dim_geo WHERE geo_type = 'state' AND geo_code = ?", [state_abbr]
    ).fetchone()
    parent_id = parent[0] if parent else None

    new_id = con.execute("SELECT COALESCE(MAX(geo_id), 0) + 1 FROM dim_geo").fetchone()[0]
    con.execute(
        """INSERT INTO dim_geo (geo_id, geo_type, geo_code, geo_name, parent_geo_id)
           VALUES (?, 'county', ?, ?, ?)""",
        [new_id, fips, county_name, parent_id],
    )
    return new_id


if __name__ == "__main__":
    seed_geo()
