"""Static-analysis findings, Git history, clones and review priorities."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..analysis import priorities, runner
from ..analysis.diagnostics.registry import tool_status
from ..models import predict as pred
from ..projects import store as pstore

router = APIRouter(prefix="/api")


def _analysis(pid: str) -> dict:
    try:
        pstore.load_meta(pid)
    except KeyError:
        raise HTTPException(404, "Project not found")
    try:
        return runner.load_analysis(pid)
    except FileNotFoundError:
        raise HTTPException(409, "Run an analysis for this project first")


@router.get("/tools")
def tools():
    """Availability of optional analysis tools (shown in Analysis setup)."""
    import shutil
    return {"static_analysis": tool_status(), "git": {"available": shutil.which("git") is not None}}


@router.get("/projects/{pid}/diagnostics")
def diagnostics(pid: str, path: Optional[str] = None, tool: Optional[str] = None, category: Optional[str] = None,
                severity: Optional[str] = None, limit: int = Query(1000, le=5000)):
    a = _analysis(pid)
    items = [d for d in a.get("diagnostics", []) if (path is None or d["path"] == path) and (tool is None or d["tool"] == tool)
             and (category is None or d["category"] == category) and (severity is None or d["severity"] == severity)]
    rank = {"high": 0, "warning": 1, "info": 2}
    items.sort(key=lambda d: (rank[d["severity"]], d["path"], d["range"]["start_line"]))
    return {"total": len(items), "items": items[:limit], "summary": a.get("diagnostics_summary"), "tools": a.get("tool_status", [])}


@router.get("/projects/{pid}/history")
def history(pid: str):
    a = _analysis(pid)
    hist = a.get("history")
    passes = {p["name"]: p for p in a["passes"]}
    reason = (passes.get("git_history") or {}).get("message", "")
    return {"available": bool(hist), "reason": None if hist else reason or "History analysis did not run",
            "history": hist, "complexity_history": a.get("complexity_history")}


@router.get("/projects/{pid}/clones")
def clones(pid: str):
    return _analysis(pid).get("clone_groups", [])


@router.get("/projects/{pid}/priorities")
def review_priorities(pid: str, model_id: Optional[str] = None):
    a = _analysis(pid)
    predictions = pred.load_predictions(pid, a["analysis_id"], model_id) if model_id else None
    return priorities.compute(a, predictions)
