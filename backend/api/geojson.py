"""Serve static geographic boundary files to the frontend map.

Mirrors measles-hotspot's pattern (backend owns geospatial reference data,
not duplicated into frontend/public).
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

GEOJSON_DIR = Path(__file__).parent.parent.parent / "data" / "geojson"


@router.get("/api/geojson/states")
def get_states_geojson():
    return FileResponse(GEOJSON_DIR / "us-states.json", media_type="application/json")
