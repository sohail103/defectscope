from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from .. import jobs
from ..analysis import runner
from ..analysis.registry import describe_passes
from ..core import config
from ..core.schemas import AnalysisConfig
from ..projects import extract, store

router = APIRouter(prefix="/api")


def _meta(pid: str):
    try:
        return store.load_meta(pid)
    except KeyError:
        raise HTTPException(404, "Project not found")


def _analysis(pid: str, aid: Optional[str] = None) -> dict:
    _meta(pid)
    try:
        return runner.load_analysis(pid, aid)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ------------------------------------------------------------------ import
@router.post("/projects/upload-zip")
async def upload_zip(request: Request):
    form = await request.form(max_files=10, max_fields=20)
    f = form.get("file")
    if f is None or not hasattr(f, "file"):
        raise HTTPException(400, "Provide a ZIP file in the 'file' field")
    f.file.seek(0, 2)
    if f.file.tell() > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Upload exceeds {config.MAX_UPLOAD_BYTES // config.MB} MB limit")
    f.file.seek(0)
    name = (f.filename or "project").rsplit("/", 1)[-1]
    name = name[:-4] if name.lower().endswith(".zip") else name
    try:
        return store.create_from_zip(name, f.file)
    except extract.ExtractionError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/upload-dir")
async def upload_dir(request: Request):
    """Directory upload: parallel `files` and `paths` fields preserve relative paths."""
    form = await request.form(max_files=config.MAX_FILES, max_fields=config.MAX_FILES * 2 + 10)
    files = [v for k, v in form.multi_items() if k == "files" and hasattr(v, "file")]
    paths = [v for k, v in form.multi_items() if k == "paths"]
    if not files:
        raise HTTPException(400, "No files received")
    items = []
    for i, f in enumerate(files):
        rel = paths[i] if i < len(paths) else (f.filename or f"file{i}")
        items.append((str(rel), await f.read()))
    name = str(form.get("name") or items[0][0].split("/")[0] or "project")
    try:
        return store.create_from_files(name, items, "directory")
    except extract.ExtractionError as e:
        raise HTTPException(400, str(e))


class SnippetIn(BaseModel):
    filename: str
    content: str


@router.post("/projects/snippet")
def snippet(body: SnippetIn):
    try:
        return store.create_from_files(body.filename, [(body.filename, body.content.encode())], "snippet")
    except extract.ExtractionError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/sample")
def sample():
    try:
        return store.create_sample()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


class LocalPathIn(BaseModel):
    path: str


@router.post("/projects/local-path")
def local_path(body: LocalPathIn):
    try:
        return store.create_from_local_path(body.path)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except FileNotFoundError:
        raise HTTPException(404, "Directory not found")


# ------------------------------------------------------------------ project info
@router.get("/projects")
def list_projects():
    return store.list_projects()


@router.get("/projects/{pid}")
def get_project(pid: str):
    meta = _meta(pid)
    latest = None
    try:
        a = runner.load_analysis(pid)
        latest = {"analysis_id": a["analysis_id"], "created_at": a["created_at"],
                  "stale": a["snapshot_hash"] != store.snapshot_hash(store.source_dir(pid))}
    except FileNotFoundError:
        pass
    return {"meta": meta, "latest_analysis": latest}


@router.delete("/projects/{pid}")
def delete_project(pid: str):
    try:
        store.delete_project(pid)
    except KeyError:
        raise HTTPException(404, "Project not found")
    return {"deleted": pid}


@router.get("/projects/{pid}/tree")
def tree(pid: str):
    _meta(pid)
    t = store.build_tree(pid)
    try:
        a = runner.load_analysis(pid)
        mx = {e["path"]: e["metrics"].get("max_cyclomatic", 0) for e in a["entities"] if e["kind"] == "file"}
        hs: dict[str, int] = {}
        for h in a["hotspots"]:
            hs[h["path"]] = hs.get(h["path"], 0) + 1

        def decorate(n):
            if n["type"] == "file":
                n["max_cyclomatic"], n["hotspots"] = mx.get(n["path"]), hs.get(n["path"], 0)
            else:
                for c in n["children"]:
                    decorate(c)
        decorate(t)
    except FileNotFoundError:
        pass
    return t


@router.get("/projects/{pid}/file")
def read_file(pid: str, path: str):
    _meta(pid)
    try:
        content = store.read_text(pid, path)
    except FileNotFoundError:
        raise HTTPException(404, "File not found")
    return {"path": path, "content": content, "lines": content.count("\n") + 1}


# ------------------------------------------------------------------ analysis
@router.get("/config/defaults")
def default_config():
    return AnalysisConfig()


@router.get("/passes")
def passes():
    return describe_passes()


@router.post("/projects/{pid}/analyze")
def analyze(pid: str, cfg: Optional[AnalysisConfig] = None):
    _meta(pid)
    cfg = cfg or AnalysisConfig()

    def work(job: jobs.Job) -> dict:
        def on_progress(frac: float, msg: str) -> None:
            job.progress, job.message = frac, msg

        def on_pass(results, _res) -> None:
            job.passes = list(results)

        aid = runner.run_analysis(pid, cfg, job.cancel_event, on_progress, on_pass)
        return {"analysis_id": aid}

    return jobs.submit("analysis", work, pid).to_dict()


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    try:
        return jobs.get(job_id).to_dict()
    except KeyError:
        raise HTTPException(404, "Job not found")


@router.post("/jobs/{job_id}/cancel")
def job_cancel(job_id: str):
    try:
        return jobs.cancel(job_id).to_dict()
    except KeyError:
        raise HTTPException(404, "Job not found")


@router.get("/projects/{pid}/analysis")
def analysis_overview(pid: str, analysis_id: Optional[str] = None):
    a = _analysis(pid, analysis_id)
    stale = a["snapshot_hash"] != store.snapshot_hash(store.source_dir(pid))
    return {k: a[k] for k in ("analysis_id", "project_id", "analysis_version", "created_at", "passes",
                              "discovery", "summary", "capabilities", "parse_status")} | {"stale": stale}


@router.get("/projects/{pid}/entities")
def entities(pid: str, path: Optional[str] = None, kind: Optional[str] = None,
             sort: Optional[str] = None, limit: int = Query(500, le=5000)):
    a = _analysis(pid)
    items = [e for e in a["entities"] if (path is None or e["path"] == path) and (kind is None or e["kind"] == kind)]
    if sort:
        items.sort(key=lambda e: -e["metrics"].get(sort, 0))
    return items[:limit]


@router.get("/projects/{pid}/hotspots")
def hotspots(pid: str, path: Optional[str] = None, severity: Optional[str] = None,
             layer: Optional[str] = None, rule: Optional[str] = None):
    a = _analysis(pid)
    return [h for h in a["hotspots"]
            if (path is None or h["path"] == path) and (severity is None or h["severity"] == severity)
            and (layer is None or h["layer"] == layer) and (rule is None or h["rule"] == rule)]


@router.get("/projects/{pid}/graph")
def graph(pid: str):
    return _analysis(pid).get("dependency_graph") or {"nodes": [], "edges": [], "cycles": []}


@router.get("/projects/{pid}/export/metrics.csv")
def export_csv(pid: str, kind: str = "function"):
    a = _analysis(pid)
    rows = [e for e in a["entities"] if e["kind"] == kind]
    keys = sorted({k for e in rows for k in e["metrics"]})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["path", "name", "kind", "language", "start_line", "end_line"] + keys)
    for e in rows:
        w.writerow([e["path"], e["qualified_name"], e["kind"], e["language"], e["range"]["start_line"],
                    e["range"]["end_line"]] + [e["metrics"].get(k, "") for k in keys])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{kind}_metrics.csv"'})


@router.get("/projects/{pid}/export/analysis.json")
def export_json(pid: str):
    a = _analysis(pid)
    import json
    return Response(json.dumps(a), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="analysis.json"'})
