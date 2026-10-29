"""FastAPI application entry point.

Run from the backend/ directory:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import jobs
from .database import init_db
from .routers import projects, render, system

app = FastAPI(title="SCP Shorts Studio", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(render.router)
app.include_router(system.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    jobs.reset_stale_jobs()


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve the built frontend if present (production single-command mode).
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
