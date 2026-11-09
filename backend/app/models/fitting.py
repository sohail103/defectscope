"""Fit a pipeline + calibrator + decision threshold using training data only.

Calibration and the decision threshold are learned from *inner out-of-fold* scores of the training set, so the
held-out data never influences them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.base import clone
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import matthews_corrcoef
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from ..preprocessing.pipelines import build_pipeline


class Calibrator:
    """Maps raw scores to calibrated probabilities. method: none | sigmoid (Platt) | isotonic."""

    def __init__(self, method: str = "none"):
        self.method = method
        self._m = None

    def fit(self, scores, y):
        s = np.asarray(scores, float)
        if self.method == "sigmoid":
            self._m = LogisticRegression(C=1e6, max_iter=1000).fit(self._logit(s).reshape(-1, 1), y)
        elif self.method == "isotonic":
            self._m = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(s, y)
        elif self.method != "none":
            raise ValueError(f"Unknown calibration method {self.method!r}")
        return self

    @staticmethod
    def _logit(s):
        s = np.clip(s, 1e-6, 1 - 1e-6)
        return np.log(s / (1 - s))

    def transform(self, scores):
        s = np.asarray(scores, float)
        if self.method == "sigmoid":
            return self._m.predict_proba(self._logit(s).reshape(-1, 1))[:, 1]
        if self.method == "isotonic":
            return self._m.predict(s)
        return s


def best_threshold(y, p, grid=None) -> float:
    """Threshold maximising MCC on the given (out-of-fold) scores. Falls back to 0.5 if scores are constant."""
    p = np.asarray(p)
    if np.ptp(p) == 0:
        return 0.5
    grid = grid if grid is not None else np.unique(np.quantile(p, np.linspace(0.05, 0.98, 60)))
    best, best_m = 0.5, -2.0
    for t in grid:
        pred = (p >= t).astype(int)
        if pred.min() == pred.max():
            continue
        m = matthews_corrcoef(y, pred)
        if m > best_m:
            best, best_m = float(t), m
    return best


@dataclass
class FittedModel:
    pipeline: object
    calibrator: Calibrator
    threshold: float
    algorithm: str
    features: list
    inner_oof_scores: Optional[np.ndarray] = None

    def raw_scores(self, X):
        return self.pipeline.predict_proba(X[self.features])[:, 1]

    def predict_proba(self, X):
        return self.calibrator.transform(self.raw_scores(X))


def fit_model(X, y, algorithm: str, params: dict | None, seed: int, calibration: str = "none",
              threshold_strategy: str = "oof_mcc", inner_splits: int = 3) -> FittedModel:
    features = list(X.columns)
    pipe = build_pipeline(algorithm, params, seed)
    need_oof = algorithm != "dummy" and (calibration != "none" or threshold_strategy == "oof_mcc")
    oof = None
    cal = Calibrator("none")
    thr = 0.5
    if need_oof:
        min_class = int(min(np.bincount(np.asarray(y).astype(int), minlength=2)))
        k = max(2, min(inner_splits, min_class))
        cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
        oof = cross_val_predict(clone(pipe), X, y, cv=cv, method="predict_proba")[:, 1]
        if calibration != "none":
            cal = Calibrator(calibration).fit(oof, y)
        if threshold_strategy == "oof_mcc":
            thr = best_threshold(y, cal.transform(oof))
    pipe.fit(X, y)
    return FittedModel(pipe, cal, thr, algorithm, features, oof)
