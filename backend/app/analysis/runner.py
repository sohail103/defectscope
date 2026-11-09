"""Executes the pass pipeline for a project and persists a reproducible result."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from ..core import config
from ..core.schemas import AnalysisConfig, PassResult
from ..projects import store
from .base import PassContext
from .registry import default_manager


def run_analysis(pid: str, cfg: AnalysisConfig, cancel: Optional[threading.Event] = None,
                 on_progress: Callable[[float, str], None] = lambda f, m: None,
                 on_pass: Callable[[list[PassResult], PassResult], None] = lambda rs, r: None) -> Optional[str]:
    """Returns the analysis id, or None if cancelled."""
    meta = store.load_meta(pid)
    manager = default_manager()
    plan = manager.plan(cfg.enabled_passes)
    ctx = PassContext(root=store.source_dir(pid), config=cfg, cancel_event=cancel or threading.Event())
    results_ref: list[PassResult] = []
    state = {"done": 0, "frac": 0.0}
    n = len(plan)

    def prog(frac: float, msg: str) -> None:
        state["frac"] = frac
        on_progress((state["done"] + frac) / n, msg)

    ctx.on_progress = prog

    def handle(res: PassResult) -> None:
        if res.status in ("ok", "failed", "skipped"):
            state["done"] = sum(1 for r in results_ref if r.status in ("ok", "failed", "skipped"))
            state["frac"] = 0.0
        on_progress(state["done"] / n, f"{res.name}: {res.status}")
        on_pass(results_ref, res)

    # the manager creates PassResult objects up front; capture the list via the first callbacks
    def collect(res: PassResult) -> None:
        if not any(res is r for r in results_ref):
            results_ref.append(res)
        handle(res)

    results = manager.run(ctx, cfg.enabled_passes, on_pass=collect)
    if ctx.cancel_event.is_set():
        return None

    art = ctx.artifacts
    entities = art.get("entities", [])
    for e in entities:
        e.metrics = ctx.metrics.get(e.id, {})
    # strip heavy transient data before serialising
    aid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    doc = {
        "analysis_id": aid, "project_id": pid, "analysis_version": config.ANALYSIS_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_hash": meta.snapshot_hash,
        "config": cfg.model_dump(),
        "passes": [r.model_dump() for r in results],
        "discovery": art.get("discovery_summary", {}),
        "parse_status": art.get("parse_status", {}),
        "summary": art.get("summary"),
        "entities": [e.model_dump() for e in entities],
        "hotspots": [h.model_dump() for h in art.get("hotspots", [])],
        "dependency_graph": art.get("dependency_graph"),
        "features": art.get("mdp_features"),
        "capabilities": {
            "analysis_level": "syntax",
            "semantic_analysis": False,
            "note": "Tree-sitter syntax-level analysis. No macro expansion, type resolution or data-flow analysis.",
            "defect_prediction": None,
        },
    }
    out = store.analyses_dir(pid) / f"{aid}.json"
    out.write_text(json.dumps(doc))
    (store.analyses_dir(pid) / "latest.txt").write_text(aid)
    return aid


def load_analysis(pid: str, aid: Optional[str] = None) -> dict:
    d = store.analyses_dir(pid)
    if aid is None:
        latest = d / "latest.txt"
        if not latest.exists():
            raise FileNotFoundError("No analysis has been run for this project")
        aid = latest.read_text().strip()
    f = d / f"{aid}.json"
    if not f.exists():
        raise FileNotFoundError(aid)
    return _cached(f)


_cache: dict = {}
_lock = threading.Lock()


def _cached(f) -> dict:
    key, mtime = str(f), f.stat().st_mtime
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
    data = json.loads(f.read_text())
    with _lock:
        _cache.clear()  # keep at most one analysis resident
        _cache[key] = (mtime, data)
    return data
