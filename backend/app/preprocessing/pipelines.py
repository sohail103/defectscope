"""Leakage-safe preprocessing + estimator pipelines.

Every transformer (imputer, log transform, scaler) lives *inside* the sklearn Pipeline, so it is fit on
training data only whenever the pipeline is fit, including inside every cross-validation fold.
Outliers are never removed: heavy-tailed metrics are handled by a log1p transform for linear models.
"""
from __future__ import annotations

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from sklearn.tree import DecisionTreeClassifier

ALGORITHMS: dict[str, dict] = {
    "dummy": {"label": "Dummy (class prior)", "scale": False,
              "defaults": {}, "allowed": set()},
    "logistic": {"label": "Logistic regression", "scale": True,
                 "defaults": {"C": 1.0, "class_weight": None, "max_iter": 2000},
                 "allowed": {"C", "class_weight", "max_iter", "penalty"}},
    "tree": {"label": "Decision tree", "scale": False,
             "defaults": {"max_depth": 5, "min_samples_leaf": 10, "class_weight": None},
             "allowed": {"max_depth", "min_samples_leaf", "min_samples_split", "class_weight"}},
    "forest": {"label": "Random forest", "scale": False,
               "defaults": {"n_estimators": 200, "min_samples_leaf": 3, "max_depth": None, "class_weight": None},
               "allowed": {"n_estimators", "min_samples_leaf", "max_depth", "max_features", "class_weight"}},
    "gboost": {"label": "Gradient boosting", "scale": False,
               "defaults": {"n_estimators": 150, "learning_rate": 0.05, "max_depth": 3, "subsample": 0.8},
               "allowed": {"n_estimators", "learning_rate", "max_depth", "subsample", "min_samples_leaf"}},
}


def _log1p(x):
    return np.log1p(np.clip(x, 0, None))


def resolve_params(algorithm: str, params: dict | None) -> dict:
    spec = ALGORITHMS[algorithm]
    params = params or {}
    bad = set(params) - spec["allowed"]
    if bad:
        raise ValueError(f"Parameters not allowed for {algorithm}: {sorted(bad)}")
    return {**spec["defaults"], **params}


def make_estimator(algorithm: str, params: dict, seed: int):
    if algorithm == "dummy":
        return DummyClassifier(strategy="prior")
    if algorithm == "logistic":
        return LogisticRegression(random_state=seed, **params)
    if algorithm == "tree":
        return DecisionTreeClassifier(random_state=seed, **params)
    if algorithm == "forest":
        return RandomForestClassifier(random_state=seed, n_jobs=-1, **params)
    if algorithm == "gboost":
        return GradientBoostingClassifier(random_state=seed, **params)
    raise KeyError(algorithm)


def build_pipeline(algorithm: str, params: dict | None = None, seed: int = 42) -> Pipeline:
    p = resolve_params(algorithm, params)
    steps = [("impute", SimpleImputer(strategy="median"))]
    if ALGORITHMS[algorithm]["scale"]:
        steps += [("log1p", FunctionTransformer(_log1p, feature_names_out="one-to-one")), ("scale", StandardScaler())]
    steps.append(("clf", make_estimator(algorithm, p, seed)))
    return Pipeline(steps)


def describe_preprocessing(algorithm: str) -> list[str]:
    d = ["Median imputation (fit on training data only; the NASA data has no missing values, but uploaded code might)"]
    if ALGORITHMS[algorithm]["scale"]:
        d += ["log(1+x) transform to tame heavy-tailed metrics", "Standardisation (fit on training data only)"]
    else:
        d.append("No scaling (tree models are invariant to monotone transforms)")
    d.append("No oversampling and no outlier removal")
    return d
