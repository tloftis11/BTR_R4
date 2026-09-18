import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.sources import router as sources_router
from api.map import router as map_router
from api.geojson import router as geojson_router

app = FastAPI(
    title="Biothreat Radar API",
    description="Unified wastewater / syndromic / genomic / travel biosurveillance signals.",
    version="0.1.0",
)

_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
origins = [o.strip() for o in _origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sources_router)
app.include_router(map_router)
app.include_router(geojson_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the frontend build in production. Must come last -- it's a catch-all.
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
