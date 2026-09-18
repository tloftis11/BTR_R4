import os
import threading
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "../data/biothreat.duckdb")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_conn: duckdb.DuckDBPyConnection | None = None
_init_lock = threading.Lock()


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a fresh DuckDB cursor for the calling thread.

    FastAPI runs each sync endpoint in its own threadpool thread, and a single
    DuckDB connection object is NOT safe for concurrent queries across threads
    (confirmed the hard way: parallel requests corrupted each other's result
    sets, surfacing as nondeterministic "too many values to unpack" errors).
    DuckDB's documented fix is Connection.cursor() -- an independent handle on
    the same database, safe for concurrent per-thread use. The one-time
    underlying connection + schema init is guarded by a lock so concurrent
    cold-start requests don't race to create it twice.

    Unlike measles-hotspot's db.py, this does NOT seed synthetic observational
    data — dim_source/dim_pathogen/dim_geo are legitimate static reference data
    (populated by backend/seed/*.py), but fact_observation is only ever written
    by the real ETL scripts in backend/etl/.
    """
    global _conn
    if _conn is None:
        with _init_lock:
            if _conn is None:  # re-check: another thread may have won the race
                db_file = Path(DB_PATH).resolve()
                db_file.parent.mkdir(parents=True, exist_ok=True)
                _conn = duckdb.connect(str(db_file))
                _ensure_schema(_conn)
    return _conn.cursor()


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_PATH.read_text())
