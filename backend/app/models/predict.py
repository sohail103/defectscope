"""Apply a registered model to an analysed project, with explicit compatibility checks.

Rules (from the project brief):
  * never substitute missing features with zeros;
  * never predict when the model's feature schema cannot be satisfied;
  * never apply a model to a language it was not trained on;
  * predictions are function-level (module-level) only and are never spread over lines.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from ..core import config
from ..explainability.explain import local_explanation
from ..projects import store as pstore
from .store import load_manifest, load_model


class IncompatibleModel(Exception):
    def __init__(self, detail: dict):
        super().__init__(detail["summary"])
        self.detail = detail


def check_compat(manifest: dict, features: dict | None) -> dict:
    reasons: list[str] = []
    required = manifest["features"]
    if not features or not features.get("rows"):
        reasons.append("The analysis has no measurable C/C++ functions, so there is nothing this model can be applied to.")
        return {"compatible": False, "summary": reasons[0], "reasons": reasons, "feature_table": [], "predictable_rows": 0,
                "excluded_by_language": {}}
    avail = set(features["available_features"])
    table = []
    for n in required:
        st = features["status"].get(n, {})
        table.append({"feature": n, "available": n in avail, "extraction": st.get("extraction", "unavailable"),
                      "source": st.get("source", ""), "caveat": st.get("caveat", ""),
                      "group": next((d["group"] for d in manifest["feature_definitions"] if d["name"] == n), "")})
    missing = [t["feature"] for t in table if not t["available"]]
    if missing:
        reasons.append("This model needs features DefectScope cannot measure on source code: " + ", ".join(missing) + ".")
    langs = set(manifest["supported_languages"])
    rows = [r for r in features["rows"] if r["language"] in langs]
    excluded = {}
    for r in features["rows"]:
        if r["language"] not in langs:
            excluded[r["language"]] = excluded.get(r["language"], 0) + 1
    for lang, n in features.get("unsupported_languages", {}).items():
        excluded[lang] = excluded.get(lang, 0) + n
    if not rows and not missing:
        reasons.append(f"The model was trained on {', '.join(sorted(langs))} code, but this project's measurable functions are "
                       f"{', '.join(features['languages_covered'])}.")
    return {"compatible": not reasons, "summary": reasons[0] if reasons else "Compatible", "reasons": reasons,
            "feature_table": table, "predictable_rows": len(rows), "excluded_by_language": excluded,
            "has_approximate_features": any(t["extraction"] == "approximate" for t in table)}


def predict_project(pid: str, analysis: dict, model_id: str) -> dict:
    manifest = load_manifest(model_id)
    compat = check_compat(manifest, analysis.get("features"))
    if not compat["compatible"]:
        raise IncompatibleModel(compat)
    fm = load_model(model_id)
    stats = manifest["training_statistics"]["features"]
    langs = set(manifest["supported_languages"])
    rows = [r for r in analysis["features"]["rows"] if r["language"] in langs]
    skipped = []
    keep = []
    for r in rows:
        vals = [r["values"].get(f) for f in manifest["features"]]
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in vals):
            skipped.append({"entity_id": r["entity_id"], "reason": "missing feature value"})
        else:
            keep.append(r)
    X = pd.DataFrame([{f: r["values"][f] for f in manifest["features"]} for r in keep], columns=manifest["features"])
    prob = fm.predict_proba(X)
    order = prob.argsort().argsort()
    ents = {e["id"]: e for e in analysis["entities"]}
    out = []
    for i, r in enumerate(keep):
        oor = [f for f in manifest["features"] if r["values"][f] < stats[f]["min"] or r["values"][f] > stats[f]["max"]]
        e = ents.get(r["entity_id"], {})
        out.append({
            "entity_id": r["entity_id"], "path": r["path"], "name": r["name"], "language": r["language"],
            "start_line": r["start_line"], "end_line": (e.get("range") or {}).get("end_line", r["start_line"]),
            "probability": float(prob[i]), "flagged": bool(prob[i] >= fm.threshold),
            "percentile_in_project": round(100.0 * order[i] / max(1, len(keep) - 1), 1),
            "out_of_training_range": oor,
            "cyclomatic": (e.get("metrics") or {}).get("cyclomatic"), "sloc": (e.get("metrics") or {}).get("sloc"),
            "nesting_depth": (e.get("metrics") or {}).get("nesting_depth"),
        })
    hist, edges = np.histogram(prob, bins=10, range=(0, 1))
    doc = {
        "project_id": pid, "analysis_id": analysis["analysis_id"], "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "granularity": "function (module-level)", "layer": "predicted_risk",
        "model": {k: manifest[k] for k in ("id", "name", "algorithm_label", "calibration", "decision_threshold", "supported_languages",
                                           "training_defect_rate", "training_rows")} | {"training_projects": [d["id"] for d in manifest["training_datasets"]]},
        "compatibility": compat,
        "summary": {"predicted": len(out), "flagged": sum(p["flagged"] for p in out), "skipped": skipped,
                    "excluded_by_language": compat["excluded_by_language"],
                    "with_out_of_range_features": sum(1 for p in out if p["out_of_training_range"]),
                    "probability_histogram": {"counts": hist.tolist(), "edges": [round(x, 2) for x in edges.tolist()]},
                    "mean_probability": float(prob.mean()) if len(prob) else None},
        "predictions": sorted(out, key=lambda p: -p["probability"]),
        "caveats": [
            "These are estimates of module-level defect proneness learned from NASA projects, not detections of defects.",
            f"Probabilities reflect the training defect rate ({manifest['training_defect_rate']:.0%}); a project with a different defect rate will see different true frequencies.",
            "Input features were re-measured by DefectScope and are approximations of the original MDP metrics; distribution differences can shift scores.",
            "Predictions apply to whole functions. They are never attributed to individual lines.",
        ],
    }
    f = pstore.analyses_dir(pid) / f"pred-{analysis['analysis_id']}-{model_id}.json"
    f.write_text(json.dumps(doc))
    return doc


def load_predictions(pid: str, analysis_id: str, model_id: str) -> dict | None:
    f = pstore.analyses_dir(pid) / f"pred-{analysis_id}-{model_id}.json"
    return json.loads(f.read_text()) if f.exists() else None


def explain_entity(analysis: dict, model_id: str, entity_id: str) -> dict:
    manifest = load_manifest(model_id)
    fm = load_model(model_id)
    row = next((r for r in (analysis.get("features") or {}).get("rows", []) if r["entity_id"] == entity_id), None)
    if row is None:
        raise KeyError("No measured features for this entity (is it a C/C++ function?)")
    if row["language"] not in manifest["supported_languages"]:
        raise IncompatibleModel({"summary": "Model not trained on this language", "reasons": ["Model not trained on this language"]})
    missing = [f for f in manifest["features"] if f not in row["values"]]
    if missing:
        raise IncompatibleModel({"summary": f"Missing features: {missing}", "reasons": [f"Missing features: {missing}"]})
    exp = local_explanation(fm, manifest["training_statistics"], row["values"])
    exp["entity"] = {"id": entity_id, "name": row["name"], "path": row["path"], "start_line": row["start_line"]}
    exp["caveat"] = ("Contributions describe how the model scored this function relative to the training population. "
                     "They show correlation learned from data, not causes of defects.")
    return exp
