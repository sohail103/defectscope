"""Measure code complexity at past commits by reading blobs from the Git object database (no checkout)."""
from __future__ import annotations

import posixpath

from ...core.schemas import ExclusionRules, Thresholds
from ...parsers import treesitter as ts
from ..passes.core import SymbolIndexPass
from ..passes.metrics import LineClasses, analyse_function

EXT = {".py": "python", ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".h": "h"}
MAX_FILES_PER_SNAPSHOT = 400


def _wanted(path: str, rules: ExclusionRules) -> str | None:
    parts = path.split("/")
    skip = {d.lower() for d in rules.dirs} | ({d.lower() for d in rules.vendored_dirs} if rules.exclude_vendored else set())
    if any(p.lower() in skip for p in parts[:-1]):
        return None
    return EXT.get(posixpath.splitext(path)[1].lower())


def measure_commit(repo, sha: str, rules: ExclusionRules, thresholds: Thresholds, track: set[str]) -> dict:
    tree = repo.commit(sha).tree
    cands = []
    for blob in tree.traverse():
        if blob.type == "blob" and blob.size <= rules.max_file_bytes:
            lang = _wanted(blob.path, rules)
            if lang:
                cands.append((blob.path, lang, blob))
    cands.sort(key=lambda t: t[0])
    capped = len(cands) > MAX_FILES_PER_SNAPSHOT
    cands = cands[:MAX_FILES_PER_SNAPSHOT]
    has_cpp = any(l == "cpp" for _, l, _ in cands)
    parsers: dict[str, object] = {}
    sym = SymbolIndexPass()
    ccs, sloc, per_file = [], 0, {}
    for path, lang, blob in cands:
        lang = ("cpp" if has_cpp else "c") if lang == "h" else lang
        try:
            src = blob.data_stream.read()
            pf = ts.parse_source(path, lang, src, parsers.setdefault(lang, ts.new_parser(lang)))  # type: ignore[arg-type]
            nodes: dict = {}
            ents = sym._extract(pf, nodes)
            sloc += LineClasses(pf).code(1, max(1, src.count(b"\n") + 1))
        except Exception:  # noqa: BLE001 - old revisions may not parse; skip the file
            continue
        file_cc = []
        for e in ents:
            if e.kind == "function":
                cc = analyse_function(nodes[e.id], ts.SPECS[lang])[0]["cyclomatic"]
                ccs.append(cc); file_cc.append(cc)
        if path in track:
            per_file[path] = max(file_cc) if file_cc else 0
    return {
        "files": len(cands), "functions": len(ccs), "sloc": sloc, "total_cyclomatic": sum(ccs),
        "mean_cyclomatic": round(sum(ccs) / len(ccs), 2) if ccs else 0, "max_cyclomatic": max(ccs, default=0),
        "high_complexity_functions": sum(1 for c in ccs if c >= thresholds.cyclomatic_warning),
        "per_file_max_cyclomatic": per_file, "capped": capped,
    }
