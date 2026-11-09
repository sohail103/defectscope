"""Secure archive extraction and file ingestion.

Nothing in an uploaded project is ever executed. Archive entries are validated
(no path traversal, no symlinks, size/ratio/file-count limits) before being written.
"""
from __future__ import annotations

import posixpath
import stat
import zipfile
from pathlib import Path
from typing import BinaryIO, Iterable

from ..core import config

# Never worth extracting (dependency caches); everything else is kept so users can
# later change exclusion rules without re-uploading.
SKIP_ON_EXTRACT = {"node_modules", ".venv", "venv", "site-packages", "__pycache__"}


class ExtractionError(ValueError):
    pass


def safe_relpath(name: str) -> str:
    """Normalise an archive/upload path and reject anything that could escape the root."""
    name = name.replace("\\", "/")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ExtractionError(f"Absolute path rejected: {name!r}")
    norm = posixpath.normpath(name)
    parts = norm.split("/")
    if norm in ("", ".") or ".." in parts:
        raise ExtractionError(f"Path traversal rejected: {name!r}")
    return norm


def _skipped(rel: str) -> bool:
    return any(p in SKIP_ON_EXTRACT for p in rel.split("/"))


def _strip_common_root(paths: list[str]) -> str:
    """If every path lives under one top-level directory, return that prefix."""
    tops = {p.split("/", 1)[0] for p in paths if "/" in p}
    flat = [p for p in paths if "/" not in p]
    if len(tops) == 1 and not flat:
        return next(iter(tops)) + "/"
    return ""


def extract_zip(src: BinaryIO, dest: Path) -> tuple[int, list[str]]:
    """Extract a ZIP into `dest`. Returns (files_written, warnings)."""
    warnings: list[str] = []
    try:
        zf = zipfile.ZipFile(src)
    except zipfile.BadZipFile as e:
        raise ExtractionError("Not a valid ZIP archive") from e

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > config.MAX_FILES:
        raise ExtractionError(f"Archive has {len(infos)} files (limit {config.MAX_FILES})")
    declared = sum(i.file_size for i in infos)
    compressed = sum(i.compress_size for i in infos) or 1
    if declared > config.MAX_EXTRACTED_BYTES:
        raise ExtractionError("Archive expands beyond the configured extraction limit")
    if declared / compressed > config.MAX_COMPRESSION_RATIO and declared > 50 * config.MB:
        raise ExtractionError("Suspicious compression ratio (possible zip bomb)")

    cleaned: list[tuple[zipfile.ZipInfo, str]] = []
    for info in infos:
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            warnings.append(f"Skipped symlink: {info.filename}")
            continue
        try:
            rel = safe_relpath(info.filename)
        except ExtractionError:
            raise  # reject the whole archive: a traversal entry is a hostile signal
        cleaned.append((info, rel))

    prefix = _strip_common_root([r for _, r in cleaned])
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    written = total = 0
    for info, rel in cleaned:
        rel = rel[len(prefix):] if prefix else rel
        if not rel or _skipped(rel):
            continue
        target = (root / rel).resolve()
        if root not in target.parents:  # belt and braces after normalisation
            raise ExtractionError(f"Path escapes extraction root: {rel!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as fin, open(target, "wb") as fout:
            while chunk := fin.read(1 << 16):
                total += len(chunk)
                if total > config.MAX_EXTRACTED_BYTES:  # header sizes can lie
                    raise ExtractionError("Extraction limit exceeded while writing")
                fout.write(chunk)
        written += 1
    return written, warnings


def write_uploaded_files(items: Iterable[tuple[str, bytes]], dest: Path) -> tuple[int, list[str]]:
    """Write browser directory-upload files (relative paths preserved)."""
    warnings: list[str] = []
    items = list(items)
    if len(items) > config.MAX_FILES:
        raise ExtractionError(f"Too many files ({len(items)}; limit {config.MAX_FILES})")
    rels = [safe_relpath(n) for n, _ in items]
    prefix = _strip_common_root(rels)
    root = dest.resolve()
    root.mkdir(parents=True, exist_ok=True)
    total = written = 0
    for rel, (_, data) in zip(rels, items):
        rel = rel[len(prefix):] if prefix else rel
        if not rel or _skipped(rel):
            continue
        total += len(data)
        if total > config.MAX_EXTRACTED_BYTES:
            raise ExtractionError("Upload exceeds the configured size limit")
        target = (root / rel).resolve()
        if root not in target.parents:
            raise ExtractionError(f"Path escapes root: {rel!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written += 1
    return written, warnings
