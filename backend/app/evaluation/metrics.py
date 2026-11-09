from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, brier_score_loss, confusion_matrix,
                             f1_score, matthews_corrcoef, precision_score, recall_score, roc_auc_score)


def classification_metrics(y_true, proba, threshold: float) -> dict:
    y = np.asarray(y_true).astype(int)
    p = np.asarray(proba, dtype=float)
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    both = len(np.unique(y)) == 2
    return {
        "threshold": float(threshold), "n": int(len(y)), "prevalence": float(y.mean()),
        "accuracy": float((pred == y).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if both else None,
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if (tn + fp) else None,
        "f1": float(f1_score(y, pred, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, pred)) if both and len(np.unique(pred)) > 1 else 0.0,
        "roc_auc": float(roc_auc_score(y, p)) if both and np.ptp(p) > 0 else (0.5 if both else None),
        "pr_auc": float(average_precision_score(y, p)) if both else None,
        "brier": float(brier_score_loss(y, p)),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


METRIC_KEYS = ["accuracy", "balanced_accuracy", "precision", "recall", "specificity", "f1", "mcc", "roc_auc", "pr_auc", "brier"]


def aggregate(folds: list[dict]) -> dict:
    out = {}
    for k in METRIC_KEYS:
        vals = [f[k] for f in folds if f.get(k) is not None]
        out[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0} if vals else None
    return out


def reliability(y_true, proba, n_bins: int = 10) -> dict:
    """Quantile-binned reliability curve + expected calibration error."""
    y, p = np.asarray(y_true), np.asarray(proba)
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    if len(edges) < 3:
        edges = np.array([p.min(), p.mean(), p.max() + 1e-9])
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, len(edges) - 2)
    bins, ece = [], 0.0
    for b in range(len(edges) - 1):
        m = idx == b
        if not m.any():
            continue
        mp, fo = float(p[m].mean()), float(y[m].mean())
        bins.append({"mean_predicted": mp, "observed_rate": fo, "count": int(m.sum())})
        ece += m.mean() * abs(mp - fo)
    hist, hedges = np.histogram(p, bins=20, range=(0, 1))
    return {"bins": bins, "ece": float(ece), "brier": float(np.mean((p - y) ** 2)),
            "histogram": {"counts": hist.tolist(), "edges": [round(x, 3) for x in hedges.tolist()]}}


def threshold_table(y_true, proba, thresholds=None) -> list[dict]:
    """Precision/recall trade-off across thresholds (descriptive; not used for tuning)."""
    thresholds = thresholds if thresholds is not None else np.linspace(0.05, 0.95, 19)
    return [{k: v for k, v in classification_metrics(y_true, proba, t).items()
             if k in ("threshold", "precision", "recall", "specificity", "f1", "mcc", "tp", "fp", "tn", "fn")} for t in thresholds]
