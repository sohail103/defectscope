"""Experiments B-F from the research brief (A is reported as unavailable for the NASA data).

All numbers come from actual model fits. Splits are stratified, seeds are recorded, and preprocessing,
calibration and thresholds are fit inside each training fold (see models/fitting.py).
"""
from __future__ import annotations

import json
import platform
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd
import sklearn
from scipy import stats
from sklearn.metrics import precision_recall_curve, roc_curve
from sklearn.model_selection import RepeatedStratifiedKFold

from ..analysis.base import AnalysisCancelled
from ..core import config
from ..datasets.registry import get_adapter
from ..features import schemas as fs
from ..models.fitting import fit_model
from ..preprocessing.pipelines import ALGORITHMS, resolve_params
from .metrics import aggregate, classification_metrics, reliability, threshold_table

KINDS = {
    "static_vs_history": "A. Static versus historical metrics",
    "algorithm_comparison": "B. Algorithm comparison (within project)",
    "cross_project": "C. Cross-project generalisation (leave-one-project-out)",
    "calibration": "D. Probability calibration",
    "ablation": "E. Feature-group ablation",
    "error_analysis": "F. Error analysis",
}


@dataclass
class ExperimentConfig:
    kind: str
    projects: list = field(default_factory=lambda: ["CM1", "JM1", "KC1", "PC1"])
    version: str = "cleaned_DDprime"
    feature_set: str = "mdp21"              # mdp21 | mdp_extractable
    algorithms: list = field(default_factory=lambda: ["dummy", "logistic", "tree", "forest", "gboost"])
    params: dict = field(default_factory=dict)  # algorithm -> hyperparameter overrides
    seed: int = 42
    n_splits: int = 5
    n_repeats: int = 2
    threshold_strategy: str = "oof_mcc"       # oof_mcc | fixed_0.5
    calibration: str = "none"
    focus_algorithm: str = "forest"           # for ablation / error analysis / calibration
    focus_project: str = "JM1"


class Run:
    """Progress + cancellation handle."""

    def __init__(self, total: int, cb: Callable[[float, str], None], cancel: threading.Event):
        self.total, self.done, self.cb, self.cancel = max(1, total), 0, cb, cancel

    def tick(self, msg: str = "") -> None:
        if self.cancel.is_set():
            raise AnalysisCancelled()
        self.done += 1
        self.cb(min(1.0, self.done / self.total), msg)


# ------------------------------------------------------------------ data
def _load(cfg: ExperimentConfig, projects: list[str]) -> dict:
    ad = get_adapter("nasa_mdp")
    feats = fs.feature_names(cfg.feature_set)
    out = {}
    for p in projects:
        ds = ad.common_schema_frame(p, cfg.version)
        ds.X = ds.X[feats]
        out[p] = ds
    return out


def _fit_kwargs(cfg: ExperimentConfig, algo: str) -> dict:
    return dict(algorithm=algo, params=cfg.params.get(algo), seed=cfg.seed, calibration=cfg.calibration,
                threshold_strategy=cfg.threshold_strategy)


def cv_eval(X: pd.DataFrame, y: pd.Series, cfg: ExperimentConfig, algo: str, run: Optional[Run] = None,
            calibration: Optional[str] = None, n_repeats: Optional[int] = None) -> dict:
    """Repeated stratified CV. Returns per-fold metrics and out-of-fold predictions per repeat."""
    reps = n_repeats or cfg.n_repeats
    rskf = RepeatedStratifiedKFold(n_splits=cfg.n_splits, n_repeats=reps, random_state=cfg.seed)
    kw = _fit_kwargs(cfg, algo)
    if calibration is not None:
        kw["calibration"] = calibration
    folds, oof, thr = [], [np.full(len(y), np.nan) for _ in range(reps)], [np.full(len(y), np.nan) for _ in range(reps)]
    for i, (tr, te) in enumerate(rskf.split(X, y)):
        fm = fit_model(X.iloc[tr], y.iloc[tr], **kw)
        p = fm.predict_proba(X.iloc[te])
        folds.append(classification_metrics(y.iloc[te], p, fm.threshold))
        oof[i // cfg.n_splits][te] = p
        thr[i // cfg.n_splits][te] = fm.threshold
        if run:
            run.tick(f"{algo} fold {i + 1}")
    return {"folds": folds, "summary": aggregate(folds), "oof": oof, "thr": thr}


def _curves(y, p) -> dict:
    fpr, tpr, _ = roc_curve(y, p)
    pr, rc, _ = precision_recall_curve(y, p)
    sel = lambda a: np.unique(np.linspace(0, len(a) - 1, min(len(a), 80)).astype(int))
    fi, pi = sel(fpr), sel(pr)
    return {"roc": [[float(fpr[i]), float(tpr[i])] for i in fi], "pr": [[float(rc[i]), float(pr[i])] for i in pi]}


def _provenance(datasets: dict) -> list[dict]:
    return [{"id": d.dataset_id, "version": d.version, "rows": d.n, "defect_rate": round(float(d.y.mean()), 4),
             "sha256": d.provenance.get("sha256"), "language": d.language} for d in datasets.values()]


# ------------------------------------------------------------------ B. algorithm comparison
def exp_algorithm_comparison(cfg: ExperimentConfig, run: Run) -> dict:
    data = _load(cfg, cfg.projects)
    per_project = {}
    for name, ds in data.items():
        rows = []
        for algo in cfg.algorithms:
            r = cv_eval(ds.X, ds.y, cfg, algo, run)
            p0 = r["oof"][0]
            rows.append({
                "algorithm": algo, "label": ALGORITHMS[algo]["label"], "params": resolve_params(algo, cfg.params.get(algo)),
                "summary": r["summary"], "fold_roc_auc": [f["roc_auc"] for f in r["folds"]],
                "pooled_oof_repeat0": classification_metrics(ds.y, p0, float(np.nanmean(r["thr"][0]))),
                "curves": _curves(ds.y, p0), "threshold_table": threshold_table(ds.y, p0),
            })
        per_project[name] = rows
    return {"per_project": per_project, "datasets": _provenance(data),
            "notes": ["Identical stratified repeated-CV splits are used for every algorithm (same seed).",
                      "Folds from repeated CV are correlated: differences smaller than one standard deviation are not meaningful.",
                      "Accuracy is reported but is misleading under class imbalance; compare MCC, PR-AUC and balanced accuracy."]}


# ------------------------------------------------------------------ C. cross-project
def _ks_shift(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    ks = {c: float(stats.ks_2samp(a[c], b[c]).statistic) for c in a.columns if a[c].nunique() > 1 and b[c].nunique() > 1}
    top = sorted(ks.items(), key=lambda kv: -kv[1])[:5]
    return {"mean_ks": float(np.mean(list(ks.values()))), "top_shifted": [{"feature": k, "ks": v} for k, v in top]}


def exp_cross_project(cfg: ExperimentConfig, run: Run) -> dict:
    data = _load(cfg, cfg.projects)
    names = list(data)
    if len(names) < 2:
        raise ValueError("Cross-project evaluation needs at least two projects")
    algos = [a for a in cfg.algorithms if a != "dummy"] + ["dummy"]
    lopo, pairs, within = [], [], {}
    for algo in algos:
        for held in names:
            train = [n for n in names if n != held]
            Xtr = pd.concat([data[n].X for n in train], ignore_index=True)
            ytr = pd.concat([data[n].y for n in train], ignore_index=True)
            fm = fit_model(Xtr, ytr, **_fit_kwargs(cfg, algo))
            p = fm.predict_proba(data[held].X)
            m = classification_metrics(data[held].y, p, fm.threshold)
            lopo.append({"algorithm": algo, "held_out": held, "train": train, "held_out_language": data[held].language,
                         "train_languages": sorted({data[n].language for n in train}), "metrics": m,
                         "curves": _curves(data[held].y, p)})
            run.tick(f"{algo}: hold out {held}")
        if algo != "dummy":
            for a in names:
                for b in names:
                    if a == b:
                        continue
                    fm = fit_model(data[a].X, data[a].y, **_fit_kwargs(cfg, algo))
                    m = classification_metrics(data[b].y, fm.predict_proba(data[b].X), fm.threshold)
                    pairs.append({"algorithm": algo, "train": a, "test": b, "metrics": m,
                                  "cross_language": data[a].language != data[b].language})
            for n in names:  # within-project baseline for the generalisation gap
                within[(algo, n)] = cv_eval(data[n].X, data[n].y, cfg, algo, None, n_repeats=1)["summary"]
            run.tick(f"{algo}: pairwise + within-project baseline")
    gap = []
    for r in lopo:
        w = within.get((r["algorithm"], r["held_out"]))
        if w and r["metrics"]["roc_auc"] is not None:
            gap.append({"algorithm": r["algorithm"], "project": r["held_out"], "within_auc": w["roc_auc"]["mean"],
                        "cross_auc": r["metrics"]["roc_auc"], "within_mcc": w["mcc"]["mean"], "cross_mcc": r["metrics"]["mcc"]})
    shift = {f"{a}->{b}": _ks_shift(data[a].X, data[b].X) for a in names for b in names if a != b}
    langs = {n: data[n].language for n in names}
    return {"lopo": lopo, "pairwise": pairs, "generalisation_gap": gap, "domain_shift": shift, "languages": langs,
            "datasets": _provenance(data),
            "notes": ["Holding out KC1 (the only C++ project) tests transfer from C to C++; it is not evidence about other languages.",
                      "A drop from within-project to cross-project performance indicates domain differences "
                      "(application area, counting tool, labelling practice) rather than a model fault.",
                      "KS statistics quantify how differently each metric is distributed between projects."]}


# ------------------------------------------------------------------ D. calibration
def exp_calibration(cfg: ExperimentConfig, run: Run) -> dict:
    data = _load(cfg, [cfg.focus_project])
    ds = data[cfg.focus_project]
    out = []
    for algo in [a for a in cfg.algorithms if a in ("logistic", "forest", "gboost", "tree")] or [cfg.focus_algorithm]:
        for cal in ("none", "sigmoid", "isotonic"):
            r = cv_eval(ds.X, ds.y, cfg, algo, run, calibration=cal, n_repeats=1)
            p = r["oof"][0]
            rel = reliability(ds.y, p)
            out.append({"algorithm": algo, "calibration": cal, "summary": r["summary"], "reliability": rel,
                        "pooled_brier": rel["brier"], "ece": rel["ece"]})
    return {"project": cfg.focus_project, "results": out, "datasets": _provenance(data),
            "notes": ["Calibrators (Platt sigmoid / isotonic) are fit on inner out-of-fold scores of each training fold only.",
                      "Reliability bins are quantile bins; a well calibrated model lies on the diagonal.",
                      "Calibration is to the defect rate of the training data; a project with a different defect rate will not match."]}


# ------------------------------------------------------------------ E. ablation
def exp_ablation(cfg: ExperimentConfig, run: Run) -> dict:
    data = _load(cfg, [cfg.focus_project])
    ds = data[cfg.focus_project]
    feats = list(ds.X.columns)
    by_group = {g: [f for f in feats if fs.group_of(f) == g] for g in fs.GROUPS}
    by_group = {g: v for g, v in by_group.items() if v}
    configs = [("all features", feats)]
    for g, v in by_group.items():
        rest = [f for f in feats if f not in v]
        if rest:
            configs.append((f"without {g}", rest))
    for g, v in by_group.items():
        configs.append((f"only {g}", v))
    out = []
    for name, cols in configs:
        r = cv_eval(ds.X[cols], ds.y, cfg, cfg.focus_algorithm, run)
        out.append({"config": name, "n_features": len(cols), "features": cols, "summary": r["summary"]})
    base = out[0]["summary"]["roc_auc"]["mean"]
    for o in out:
        o["delta_auc_vs_all"] = o["summary"]["roc_auc"]["mean"] - base
    return {"project": cfg.focus_project, "algorithm": cfg.focus_algorithm, "results": out, "groups": by_group,
            "unavailable_groups": fs.UNAVAILABLE_GROUPS, "datasets": _provenance(data),
            "notes": ["Groups share information (e.g. LOC and Halstead counts are strongly correlated), so removing one group "
                      "often changes little: other groups carry the same signal. Importance is not causation."]}


# ------------------------------------------------------------------ F. error analysis
def exp_error_analysis(cfg: ExperimentConfig, run: Run) -> dict:
    data = _load(cfg, [cfg.focus_project])
    ds = data[cfg.focus_project]
    X, y = ds.X.reset_index(drop=True), ds.y.reset_index(drop=True)
    r = cv_eval(X, y, cfg, cfg.focus_algorithm, run, n_repeats=1)
    p, thr = r["oof"][0], r["thr"][0]
    pred = (p >= thr).astype(int)
    cat = np.where((y == 1) & (pred == 1), "TP", np.where((y == 0) & (pred == 1), "FP", np.where((y == 1) & (pred == 0), "FN", "TN")))
    show = [c for c in ["LOC_TOTAL", "CYCLOMATIC_COMPLEXITY", "HALSTEAD_VOLUME", "HALSTEAD_DIFFICULTY", "LOC_EXECUTABLE", "LOC_COMMENTS"] if c in X.columns]
    groups = {}
    for g in ("TP", "FP", "FN", "TN"):
        m = cat == g
        groups[g] = {"count": int(m.sum()), "mean_probability": float(p[m].mean()) if m.any() else None,
                     "median": {c: float(X.loc[m, c].median()) for c in show} if m.any() else {}}

    def smd(a, b, c):  # standardised mean difference
        sa, sb = X.loc[a, c], X.loc[b, c]
        pooled = np.sqrt((sa.var() + sb.var()) / 2) or 1.0
        return float((sa.mean() - sb.mean()) / pooled)

    contrasts = []
    for a, b, meaning in (("FN", "TP", "missed defects vs caught defects"), ("FP", "TN", "false alarms vs correctly cleared")):
        ma, mb = cat == a, cat == b
        if ma.sum() > 1 and mb.sum() > 1:
            for c in show:
                u = stats.mannwhitneyu(X.loc[ma, c], X.loc[mb, c], alternative="two-sided")
                contrasts.append({"contrast": f"{a} vs {b}", "meaning": meaning, "feature": c, "median_a": float(X.loc[ma, c].median()),
                                  "median_b": float(X.loc[mb, c].median()), "smd": smd(ma, mb, c), "p": float(u.pvalue)})
    insights = []
    for c in contrasts:
        if c["p"] < 0.01 and abs(c["smd"]) >= 0.3:
            insights.append(f"{c['meaning'].capitalize()}: median {c['feature']} is {c['median_a']:.4g} vs {c['median_b']:.4g} "
                            f"(standardised difference {c['smd']:+.2f}, Mann-Whitney p={c['p']:.1e}).")
    size_col = "LOC_TOTAL" if "LOC_TOTAL" in X.columns else show[0]
    qs = pd.qcut(X[size_col], 4, duplicates="drop")
    by_size = []
    for iv, idx in qs.groupby(qs, observed=True).groups.items():
        ii = np.array(list(idx))
        pos, neg = (y.iloc[ii] == 1), (y.iloc[ii] == 0)
        by_size.append({"bin": str(iv), "n": int(len(ii)), "defect_rate": float(y.iloc[ii].mean()),
                        "miss_rate": float((pred[ii][pos.values] == 0).mean()) if pos.any() else None,
                        "false_alarm_rate": float((pred[ii][neg.values] == 1).mean()) if neg.any() else None})
    rates = [b["miss_rate"] for b in by_size if b["miss_rate"] is not None]
    if len(rates) >= 2 and max(rates) - min(rates) > 0.2:
        insights.append(f"Miss rate varies with {size_col}: from {min(rates):.0%} to {max(rates):.0%} across size quartiles, so errors are not uniform.")
    cols = list(X.columns)

    def cases(mask, order):
        idx = np.where(mask)[0]
        idx = idx[np.argsort(p[idx])] if order == "asc" else idx[np.argsort(-p[idx])]
        return [{"row": int(i), "probability": float(p[i]), "threshold": float(thr[i]), "values": {c: float(X.iloc[i][c]) for c in cols}} for i in idx[:10]]

    return {"project": cfg.focus_project, "algorithm": cfg.focus_algorithm, "groups": groups, "contrasts": contrasts,
            "error_by_size_quartile": {"feature": size_col, "bins": by_size}, "insights": insights,
            "hardest_false_negatives": cases(cat == "FN", "asc"), "hardest_false_positives": cases(cat == "FP", "desc"),
            "datasets": _provenance(data),
            "notes": ["Predictions are out-of-fold: every row was predicted by a model that never saw it.",
                      "Rows are anonymous modules, so cases cannot be traced back to source code."]}


# ------------------------------------------------------------------ A. static vs historical
def exp_static_vs_history(cfg: ExperimentConfig, run: Run) -> dict:
    return {"status": "unavailable",
            "reason": "This experiment needs per-module development history (churn, authors, change frequency) aligned with defect labels. "
                      "The NASA MDP datasets contain only static metrics, and no history-labelled dataset has been imported. "
                      "Running it on NASA data would require fabricating history features, which DefectScope does not do.",
            "needed": "A dataset with per-file/function history features and defect labels, e.g. one mined from a repository with issue links.",
            "datasets": []}


RUNNERS = {
    "static_vs_history": (exp_static_vs_history, lambda c: 1),
    "algorithm_comparison": (exp_algorithm_comparison, lambda c: len(c.projects) * len(c.algorithms) * c.n_splits * c.n_repeats),
    "cross_project": (exp_cross_project, lambda c: (len(c.algorithms)) * (len(c.projects) + 1) + 1),
    "calibration": (exp_calibration, lambda c: 3 * 4 * c.n_splits),
    "ablation": (exp_ablation, lambda c: 8 * c.n_splits * c.n_repeats),
    "error_analysis": (exp_error_analysis, lambda c: c.n_splits),
}


def run_experiment(cfg: ExperimentConfig, cb: Callable[[float, str], None] = lambda f, m: None,
                   cancel: Optional[threading.Event] = None) -> dict:
    if cfg.kind not in RUNNERS:
        raise ValueError(f"Unknown experiment kind {cfg.kind!r}")
    fn, total = RUNNERS[cfg.kind]
    for a in cfg.algorithms:
        if a not in ALGORITHMS:
            raise ValueError(f"Unknown algorithm {a!r}")
    t0 = time.perf_counter()
    run = Run(total(cfg), cb, cancel or threading.Event())
    results = fn(cfg, run)
    doc = {
        "id": time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6], "kind": cfg.kind, "title": KINDS[cfg.kind],
        "status": "unavailable" if results.get("status") == "unavailable" else "done",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "duration_s": round(time.perf_counter() - t0, 2),
        "config": cfg.__dict__, "results": results,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(), "scikit_learn": sklearn.__version__,
                        "numpy": np.__version__, "pandas": pd.__version__},
    }
    config.EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.EXPERIMENTS_DIR / f"{doc['id']}.json").write_text(json.dumps(doc))
    return doc


def list_experiments() -> list[dict]:
    out = []
    for f in sorted(config.EXPERIMENTS_DIR.glob("*.json"), reverse=True):
        d = json.loads(f.read_text())
        out.append({k: d[k] for k in ("id", "kind", "title", "status", "created_at", "duration_s")} | {"config": d["config"]})
    return out


def load_experiment(eid: str) -> dict:
    if not eid.replace("-", "").isalnum():
        raise KeyError(eid)
    f = config.EXPERIMENTS_DIR / f"{eid}.json"
    if not f.exists():
        raise KeyError(eid)
    return json.loads(f.read_text())
