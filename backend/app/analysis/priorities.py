"""Review prioritisation: per-function factors, shown separately, with transparent top-decile flags.

There is deliberately no blended score. Each factor is reported on its own, and a function is "flagged" on a factor when
it is in the top 10% of the project for that factor (and non-trivial). The flag count is a simple, explainable way to
sort; users can re-sort by any individual factor.
"""
from __future__ import annotations

import math
from typing import Optional

FACTOR_LABELS = {
    "complexity": "cyclomatic complexity", "diagnostics": "static-analysis findings", "churn": "file change frequency",
    "fixes": "bug-fix-like commits in the file", "risk": "predicted defect risk", "duplication": "duplicated structure",
}


FUNCTION_LEVEL = {"complexity", "diagnostics", "risk", "duplication"}


def _top_decile(values: list[float]) -> Optional[float]:
    vals = sorted(v for v in values if v is not None)
    if len(vals) < 3:
        return None
    return vals[max(0, math.ceil(0.9 * len(vals)) - 1)]


def compute(analysis: dict, predictions: Optional[dict] = None) -> dict:
    ents = analysis["entities"]
    file_m = {e["path"]: e["metrics"] for e in ents if e["kind"] == "file"}
    funcs = [e for e in ents if e["kind"] == "function"]
    has_hist = bool(analysis.get("history"))
    has_diag = analysis.get("diagnostics_summary") is not None
    pred = {p["entity_id"]: p for p in (predictions or {}).get("predictions", [])}

    rows = []
    for e in funcs:
        m, fm = e["metrics"], file_m.get(e["path"], {})
        rows.append({
            "entity_id": e["id"], "name": e["qualified_name"], "path": e["path"], "language": e["language"],
            "start_line": e["range"]["start_line"], "cyclomatic": m.get("cyclomatic", 0), "nesting_depth": m.get("nesting_depth", 0),
            "sloc": m.get("sloc", 0),
            "diagnostics_high": m.get("diagnostics_high", 0) if has_diag else None,
            "diagnostics_total": m.get("diagnostics_total", 0) if has_diag else None,
            "file_commits": fm.get("git_commits") if has_hist else None,
            "file_fix_commits": fm.get("git_fix_commits") if has_hist else None,
            "file_churn": fm.get("git_churn") if has_hist else None,
            "clone_group_size": m.get("clone_group_size", 0),
            "risk": pred[e["id"]]["probability"] if e["id"] in pred else None,
            "risk_flagged": pred[e["id"]]["flagged"] if e["id"] in pred else None,
        })

    cuts = {
        "complexity": _top_decile([r["cyclomatic"] for r in rows]),
        "churn": _top_decile([r["file_commits"] for r in rows if r["file_commits"] is not None]),
        "fixes": _top_decile([r["file_fix_commits"] for r in rows if r["file_fix_commits"] is not None]),
        "risk": _top_decile([r["risk"] for r in rows if r["risk"] is not None]),
    }
    for r in rows:
        flags = []
        if cuts["complexity"] is not None and r["cyclomatic"] >= max(cuts["complexity"], 2):
            flags.append("complexity")
        if has_diag and (r["diagnostics_high"] or 0) > 0:
            flags.append("diagnostics")
        if cuts["churn"] is not None and r["file_commits"] is not None and r["file_commits"] >= max(cuts["churn"], 2):
            flags.append("churn")
        if cuts["fixes"] is not None and (r["file_fix_commits"] or 0) >= max(cuts["fixes"], 1):
            flags.append("fixes")
        if r["risk"] is not None and (r["risk_flagged"] or (cuts["risk"] is not None and r["risk"] >= cuts["risk"])):
            flags.append("risk")
        if r["clone_group_size"] >= 2:
            flags.append("duplication")
        # Churn and fix history are attributes of the *file*, so they must not outrank function-specific evidence.
        r["flags"] = flags
        r["function_flag_count"] = sum(f in FUNCTION_LEVEL for f in flags)
        r["file_flag_count"] = len(flags) - r["function_flag_count"]
    rows.sort(key=lambda r: (-r["function_flag_count"], -r["file_flag_count"], -(r["risk"] or 0), -r["cyclomatic"]))
    available = ["complexity", "duplication"] + (["diagnostics"] if has_diag else []) + (["churn", "fixes"] if has_hist else []) + \
                (["risk"] if pred else [])
    missing = {}
    if not has_hist:
        missing["churn/fixes"] = "No Git history in this analysis"
    if not pred:
        missing["risk"] = "No defect-risk model applied (Defect risk tab); only C/C++ functions can be scored"
    return {"rows": rows, "factors_available": available, "factors_unavailable": missing, "labels": FACTOR_LABELS,
            "thresholds": {k: v for k, v in cuts.items() if v is not None},
            "note": "Factors are shown separately. A flag means the function is in the project's top 10% for that factor "
                    "(diagnostics: any high-severity finding; duplication: shares its structure with another function). "
                    "Churn and fix flags describe the whole file, so rows are sorted by function-level flags first."}
