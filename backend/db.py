import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "../data/biothreat.duckdb")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_conn: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a process-wide DuckDB connection, creating the schema on first use.

    Unlike measles-hotspot's db.py, this does NOT seed synthetic observational
    data — dim_source/dim_pathogen/dim_geo are legitimate static reference data
    (populated by backend/seed/*.py), but fact_observation is only ever written
    by the real ETL scripts in backend/etl/.
    """
    global _conn
    if _conn is None:
        db_file = Path(DB_PATH).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(str(db_file))
        _ensure_schema(_conn)
    return _conn


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_PATH.read_text())
