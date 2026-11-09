"""Project persistence: each project lives in workspaces/<id>/{meta.json,source/,analyses/}."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable, Optional

from ..core import config
from ..core.schemas import AnalysisConfig, ExclusionRules, FileInfo, ProjectMeta
from . import extract
from .discovery import discover


def project_dir(pid: str) -> Path:
    if not pid.isalnum():
        raise KeyError(pid)
    return config.WORKSPACES / pid


def source_dir(pid: str) -> Path:
    return project_dir(pid) / "source"


def analyses_dir(pid: str) -> Path:
    d = project_dir(pid) / "analyses"
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshot_hash(root: Path) -> str:
    """Content hash of the whole source snapshot (used to detect stale analyses)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink() and ".git" not in p.relative_to(root).parts:
            h.update(str(p.relative_to(root).as_posix()).encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def _finish(pid: str, name: str, source: str, warnings: list[str]) -> ProjectMeta:
    root = source_dir(pid)
    files, summary = discover(root, ExclusionRules())
    summary["import_warnings"] = warnings
    meta = ProjectMeta(
        id=pid, name=name, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source=source, snapshot_hash=snapshot_hash(root), file_count=len(files),
        total_bytes=sum(f.size for f in files), summary=summary,
    )
    (project_dir(pid) / "meta.json").write_text(meta.model_dump_json(indent=2))
    return meta


def _new_id() -> str:
    pid = uuid.uuid4().hex[:12]
    project_dir(pid).mkdir(parents=True)
    return pid


def create_from_zip(name: str, fileobj: BinaryIO) -> ProjectMeta:
    pid = _new_id()
    try:
        _, warnings = extract.extract_zip(fileobj, source_dir(pid))
    except Exception:
        shutil.rmtree(project_dir(pid), ignore_errors=True)
        raise
    return _finish(pid, name, "zip", warnings)


def create_from_files(name: str, items: Iterable[tuple[str, bytes]], source: str = "directory") -> ProjectMeta:
    pid = _new_id()
    try:
        _, warnings = extract.write_uploaded_files(items, source_dir(pid))
    except Exception:
        shutil.rmtree(project_dir(pid), ignore_errors=True)
        raise
    return _finish(pid, name, source, warnings)  # type: ignore[arg-type]


def create_from_local_path(path: str) -> ProjectMeta:
    if not config.ALLOW_LOCAL_PATHS:
        raise PermissionError("Local path import is disabled. Start with DEFECTSCOPE_ALLOW_LOCAL_PATHS=1.")
    src = Path(path).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(path)
    pid = _new_id()
    dest = source_dir(pid)
    # Copy (not link) so analysis works on an immutable snapshot and never touches the original.
    shutil.copytree(
        src, dest, symlinks=False, ignore_dangling_symlinks=True,
        ignore=shutil.ignore_patterns(*extract.SKIP_ON_EXTRACT),
    )
    return _finish(pid, src.name, "local_path", [])


def create_sample() -> ProjectMeta:
    """Import the bundled example project (always allowed; the path is fixed, not user-supplied)."""
    src = config.ROOT / "examples" / "sample_project"
    if not src.is_dir():
        raise FileNotFoundError("Bundled sample project is missing")
    pid = _new_id()
    shutil.copytree(src, source_dir(pid), symlinks=False)
    return _finish(pid, "sample_project", "directory", [])


def load_meta(pid: str) -> ProjectMeta:
    f = project_dir(pid) / "meta.json"
    if not f.exists():
        raise KeyError(pid)
    return ProjectMeta.model_validate_json(f.read_text())


def list_projects() -> list[ProjectMeta]:
    out = []
    if config.WORKSPACES.exists():
        for d in sorted(config.WORKSPACES.iterdir()):
            if (d / "meta.json").exists():
                out.append(ProjectMeta.model_validate_json((d / "meta.json").read_text()))
    return sorted(out, key=lambda m: m.created_at, reverse=True)


def delete_project(pid: str) -> None:
    d = project_dir(pid)
    if not d.exists():
        raise KeyError(pid)
    shutil.rmtree(d)


def resolve_file(pid: str, rel: str) -> Path:
    root = source_dir(pid).resolve()
    p = (root / rel).resolve()
    if root not in p.parents or not p.is_file():
        raise FileNotFoundError(rel)
    return p


def read_text(pid: str, rel: str) -> str:
    return resolve_file(pid, rel).read_bytes().decode("utf-8", errors="replace")


def build_tree(pid: str, rules: Optional[ExclusionRules] = None) -> dict:
    root = source_dir(pid)
    files, summary = discover(root, rules or ExclusionRules())
    tree: dict = {"name": root.parent.name, "path": "", "type": "dir", "children": []}
    index: dict[str, dict] = {"": tree}

    def ensure_dir(path: str, excluded_reason: Optional[str] = None) -> dict:
        if path in index:
            return index[path]
        parent_path, _, name = path.rpartition("/")
        parent = ensure_dir(parent_path)
        node = {"name": name, "path": path, "type": "dir", "children": []}
        if excluded_reason:
            node["excluded"] = excluded_reason
        parent["children"].append(node)
        index[path] = node
        return node

    for d, reason in summary["excluded_directories"].items():
        if d.split("/")[-1] != ".git":
            ensure_dir(d, reason)
    for f in files:
        parent_path = f.path.rpartition("/")[0]
        ensure_dir(parent_path)["children"].append({
            "name": f.path.rpartition("/")[2], "path": f.path, "type": "file",
            "language": f.language, "role": f.role, "size": f.size,
            "excluded": f.exclusion_reason if f.excluded else None,
        })

    def sort(n: dict) -> None:
        if n["type"] == "dir":
            n["children"].sort(key=lambda c: (c["type"] != "dir", c["name"].lower()))
            for c in n["children"]:
                sort(c)

    sort(tree)
    return tree
