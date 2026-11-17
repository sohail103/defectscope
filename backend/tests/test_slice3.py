"""Slice 3: static-analysis providers, Git history, clones, review priorities. Kept small; tool-dependent tests skip if a tool is absent."""
import io
import time
import zipfile
from pathlib import Path

import pytest

from app.analysis import priorities
from app.analysis.diagnostics.categories import clang_category, cppcheck_category
from app.analysis.diagnostics.base import find_tool
from app.analysis.runner import load_analysis, run_analysis
from app.core.schemas import AnalysisConfig
from app.projects import store

needs_cppcheck = pytest.mark.skipif(find_tool("cppcheck") is None, reason="cppcheck not installed")
needs_ruff = pytest.mark.skipif(find_tool("ruff") is None, reason="ruff not installed")
DEMO = Path(__file__).resolve().parents[2] / "examples" / "demo_history_repo.zip"


def analyse(meta, cfg=None):
    run_analysis(meta.id, cfg or AnalysisConfig())
    return load_analysis(meta.id)


def test_category_mapping_uses_tool_ids_and_cwe_only():
    assert cppcheck_category("nullPointer", None) == "null_pointer"
    assert cppcheck_category("whatever", 401) == "resource_management"      # CWE wins
    assert cppcheck_category("totallyUnknownRule", None) == "maintainability"  # unknown => no invented bug type
    assert clang_category("clang-analyzer-core.NullDereference") == "null_pointer"


@needs_cppcheck
@needs_ruff
def test_planted_defects_are_found_with_entities_and_relative_paths(sample_zip):
    a = analyse(store.create_from_zip("s", sample_zip))
    cats = {(d["tool"], d["category"]) for d in a["diagnostics"]}
    assert ("cppcheck", "buffer_bounds") in cats and ("cppcheck", "resource_management") in cats
    assert ("cppcheck", "uninitialized") in cats and ("bandit", "security") in cats
    assert all(not d["path"].startswith("/") for d in a["diagnostics"])
    leak = next(d for d in a["diagnostics"] if d["rule"] == "memleak")
    assert next(e for e in a["entities"] if e["id"] == leak["entity_id"])["name"] == "leak_memory"


@needs_ruff
def test_project_supplied_tool_config_cannot_hide_findings():
    meta = store.create_from_files("evil", [("a.py", b"import os\n"), ("ruff.toml", b"[lint]\nignore = ['F401']\n"),
                                            ("pyproject.toml", b"[tool.ruff.lint]\nignore = ['F401']\n")])
    assert any(d["rule"] == "F401" for d in analyse(meta)["diagnostics"])


def test_history_on_demo_repo_and_cutoff_prevents_future_commits():
    with open(DEMO, "rb") as fh:
        meta = store.create_from_zip("demo", fh)
    a = analyse(meta)
    h = a["history"]
    assert h["commits_analysed"] == 14 and h["authors_total"] == 3
    inv = h["files"]["pylib/inventory.py"]
    assert inv["git_commits"] == 7 and inv["git_fix_commits"] == 3
    pts = a["complexity_history"]["points"]
    assert pts[0]["max_cyclomatic"] == 1 and pts[-1]["max_cyclomatic"] == 13

    cfg = AnalysisConfig()
    cfg.history.until = "2026-03-31"
    early = analyse(meta, cfg)["history"]
    assert early["commits_analysed"] == 5 and early["last_commit"] <= "2026-03-31"
    assert early["files"]["pylib/inventory.py"]["git_commits"] == 3  # later commits do not leak in


def test_optional_passes_skip_cleanly_without_git(sample_zip):
    a = analyse(store.create_from_zip("s", sample_zip))
    status = {p["name"]: p["status"] for p in a["passes"]}
    assert status["git_history"] == "skipped" and status["complexity_history"] == "skipped"
    assert status["structural_hotspots"] == "ok" and status["project_summary"] == "ok"
    assert a["history"] is None


def test_clone_detection_finds_renamed_copies(sample_zip):
    a = analyse(store.create_from_zip("s", sample_zip))
    names = [sorted(m["name"] for m in g["members"]) for g in a["clone_groups"]]
    assert ["sum_valid", "total_positive"] in names
    assert any(h["rule"] == "duplicated_structure" for h in a["hotspots"])


def test_priorities_do_not_let_file_level_history_outrank_function_evidence():
    def ent(i, name, cc, **m):
        return {"id": i, "kind": "function", "qualified_name": name, "path": "a.c", "language": "c", "range": {"start_line": 1, "end_line": 5},
                "metrics": {"cyclomatic": cc, "nesting_depth": 1, "sloc": 5, **m}}
    ents = [{"id": "a.c", "kind": "file", "path": "a.c", "metrics": {"git_commits": 50, "git_fix_commits": 20}}] + \
           [ent(f"f{i}", f"trivial{i}", 1) for i in range(8)] + [ent("bad", "bad", 1, diagnostics_high=2, diagnostics_total=2)]
    doc = {"entities": ents, "history": {"x": 1}, "diagnostics_summary": {}}
    rows = priorities.compute(doc)["rows"]
    assert rows[0]["name"] == "bad" and "diagnostics" in rows[0]["flags"]
    assert all(r["file_flag_count"] >= 1 for r in rows)  # hot file flags exist but are secondary
