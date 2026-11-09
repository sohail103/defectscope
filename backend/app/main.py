"""DefectScope backend entry point. Binds to localhost by default (see scripts/dev.sh)."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import lab, projects
from .core import config

config.ensure_dirs()
app = FastAPI(title="DefectScope", version=config.ANALYSIS_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(projects.router)
app.include_router(lab.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": config.ANALYSIS_VERSION}


# Serve the built frontend (npm run build) from the same origin when present.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = _dist / full_path
        return FileResponse(f if f.is_file() else _dist / "index.html")
