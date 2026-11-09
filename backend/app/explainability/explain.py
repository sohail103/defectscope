"""Global and local explanations.

Explanations describe what the *model* uses, not what causes defects. A feature that raises predicted risk is a
correlate learned from the training data; it is not evidence of a causal mechanism.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.model_selection import StratifiedKFold

from ..models.fitting import FittedModel
from ..preprocessing.pipelines import build_pipeline

TREE_ALGOS = {"tree", "forest", "gboost"}


def permutation_importance_cv(X: pd.DataFrame, y: pd.Series, algorithm: str, params, seed: int,
                              n_splits: int = 5, n_repeats: int = 5) -> list[dict]:
    """Permutation importance measured on held-out folds (drop in ROC-AUC when a feature is shuffled)."""
    if algorithm == "dummy":
        return []
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    acc = np.zeros((n_splits, X.shape[1]))
    for i, (tr, te) in enumerate(skf.split(X, y)):
        pipe = build_pipeline(algorithm, params, seed).fit(X.iloc[tr], y.iloc[tr])
        r = permutation_importance(pipe, X.iloc[te], y.iloc[te], scoring="roc_auc", n_repeats=n_repeats,
                                   random_state=seed, n_jobs=1)
        acc[i] = r.importances_mean
    mean, sd = acc.mean(0), acc.std(0)
    return sorted([{"feature": f, "importance": float(m), "std": float(s)} for f, m, s in zip(X.columns, mean, sd)],
                  key=lambda d: -d["importance"])


def intrinsic_importance(fm: FittedModel) -> dict:
    clf = fm.pipeline[-1]
    if fm.algorithm == "logistic":
        return {"kind": "coefficients", "note": "Coefficients on log-transformed, standardised features (log-odds per standard deviation).",
                "values": sorted([{"feature": f, "value": float(c)} for f, c in zip(fm.features, clf.coef_[0])], key=lambda d: -abs(d["value"]))}
    if hasattr(clf, "feature_importances_"):
        return {"kind": "impurity_importance", "note": "Mean decrease in impurity; biased toward high-cardinality features. Prefer permutation importance.",
                "values": sorted([{"feature": f, "value": float(c)} for f, c in zip(fm.features, clf.feature_importances_)], key=lambda d: -d["value"])}
    return {"kind": "none", "values": []}


def training_statistics(X: pd.DataFrame, fm: FittedModel) -> dict:
    """Population statistics saved with the model for comparisons and out-of-range checks."""
    q = np.linspace(0, 1, 101)
    stats = {c: {"quantiles": [float(v) for v in X[c].quantile(q)], "min": float(X[c].min()), "max": float(X[c].max()),
                 "median": float(X[c].median()), "mean": float(X[c].mean())} for c in X.columns}
    out = {"features": stats, "n": int(len(X))}
    if fm.algorithm == "logistic":
        out["transformed_mean"] = [float(v) for v in fm.pipeline[:-1].transform(X).mean(axis=0)]
    return out


def percentile(value: float, quantiles: list[float]) -> float:
    q = np.asarray(quantiles)
    lo, hi = np.searchsorted(q, value, side="left"), np.searchsorted(q, value, side="right")
    return float((lo + hi) / 2)  # percentile in [0, 100]; ties get their mid-rank


def local_explanation(fm: FittedModel, train_stats: dict, row: dict) -> dict:
    df = pd.DataFrame([{f: row[f] for f in fm.features}])
    raw = float(fm.raw_scores(df)[0])
    prob = float(fm.calibrator.transform([raw])[0])
    method, space, base, contrib, note = None, None, None, None, ""
    pre, clf = fm.pipeline[:-1], fm.pipeline[-1]
    try:
        if fm.algorithm == "dummy":
            raise ValueError("The dummy model uses no features")
        x = pre.transform(df)
        if fm.algorithm == "logistic":
            mean = np.asarray(train_stats["transformed_mean"])
            contrib = clf.coef_[0] * (x[0] - mean)
            base = float(clf.intercept_[0] + clf.coef_[0] @ mean)
            method, space = "linear (coefficient × deviation from training mean)", "log-odds"
        else:
            import shap
            ex = shap.TreeExplainer(clf)
            sv = ex.shap_values(x)
            sv = sv[1] if isinstance(sv, list) else (sv[:, :, 1] if np.ndim(sv) == 3 else sv)
            contrib = np.asarray(sv)[0]
            ev = np.ravel(ex.expected_value)
            base = float(ev[-1])
            method = "SHAP (TreeExplainer, path-dependent)"
            space = "log-odds" if fm.algorithm == "gboost" else "probability"
        model_out = (np.log(raw / (1 - raw)) if space == "log-odds" and 0 < raw < 1 else raw)
        err = abs(base + float(np.sum(contrib)) - float(model_out))
    except Exception as e:  # noqa: BLE001 - fall back to a simple, honest occlusion estimate
        if fm.algorithm == "dummy":
            return {"method": "none", "note": "The baseline model ignores all features.", "probability": prob, "raw_score": raw,
                    "threshold": fm.threshold, "contributions": []}
        method, space, note = f"occlusion fallback ({type(e).__name__})", "probability", "SHAP was unavailable; each feature was replaced by its training median."
        contrib, err = [], None
        for f in fm.features:
            alt = df.copy()
            alt[f] = train_stats["features"][f]["median"]
            contrib.append(raw - float(fm.raw_scores(alt)[0]))
        contrib, base = np.asarray(contrib), raw - float(np.sum(contrib))
    items = []
    for f, c in zip(fm.features, contrib):
        st = train_stats["features"][f]
        items.append({"feature": f, "value": float(row[f]), "contribution": float(c),
                      "training_percentile": percentile(float(row[f]), st["quantiles"]), "training_median": st["median"],
                      "outside_training_range": bool(row[f] < st["min"] or row[f] > st["max"])})
    items.sort(key=lambda d: -abs(d["contribution"]))
    return {"method": method, "space": space, "base_value": base, "raw_score": raw, "probability": prob,
            "threshold": fm.threshold, "contributions": items, "local_accuracy_error": err,
            "note": note or "Contributions explain the model's raw score before calibration. Calibration is monotonic, so ranking is unchanged."}
