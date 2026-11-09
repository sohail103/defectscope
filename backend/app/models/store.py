"""Train, persist and load models with complete manifests (dataset checksums, schema, seed, evaluation)."""
from __future__ import annotations

import json
import platform
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import joblib
import numpy as np
import pandas as pd
import sklearn

from ..core import config
from ..datasets.registry import get_adapter
from ..evaluation.experiments import ExperimentConfig, Run, cv_eval
from ..evaluation.metrics import classification_metrics
from ..explainability.explain import intrinsic_importance, permutation_importance_cv, training_statistics
from ..features import schemas as fs
from ..preprocessing.pipelines import ALGORITHMS, describe_preprocessing, resolve_params
from .fitting import FittedModel, fit_model

import threading


@dataclass
class TrainConfig:
    name: str = ""
    algorithm: str = "forest"
    params: dict = field(default_factory=dict)
    projects: list = field(default_factory=lambda: ["CM1", "JM1", "PC1"])
    version: str = "cleaned_DDprime"
    feature_set: str = "mdp_extractable"
    calibration: str = "sigmoid"
    threshold_strategy: str = "oof_mcc"
    seed: int = 42
    n_splits: int = 5


def _model_dir(mid: str):
    if not mid.replace("-", "").replace("_", "").isalnum():
        raise KeyError(mid)
    return config.MODELS_DIR / mid


def train_model(cfg: TrainConfig, cb: Callable[[float, str], None] = lambda f, m: None,
                cancel: Optional[threading.Event] = None) -> dict:
    cancel = cancel or threading.Event()
    if cfg.algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm {cfg.algorithm!r}")
    if not cfg.projects:
        raise ValueError("Choose at least one training project")
    ad = get_adapter("nasa_mdp")
    features = fs.feature_names(cfg.feature_set)
    data = {}
    for p in cfg.projects:
        ds = ad.common_schema_frame(p, cfg.version)
        ds.X = ds.X[features]
        data[p] = ds
    X = pd.concat([d.X for d in data.values()], ignore_index=True)
    y = pd.concat([d.y for d in data.values()], ignore_index=True)
    langs = sorted({d.language for d in data.values()})
    params = resolve_params(cfg.algorithm, cfg.params)
    n_lopo = len(data) if len(data) > 1 else 0
    run = Run(cfg.n_splits + n_lopo + 3, cb, cancel)

    ec = ExperimentConfig(kind="algorithm_comparison", projects=cfg.projects, version=cfg.version, feature_set=cfg.feature_set,
                          params={cfg.algorithm: cfg.params}, seed=cfg.seed, n_splits=cfg.n_splits, n_repeats=1,
                          threshold_strategy=cfg.threshold_strategy, calibration=cfg.calibration)
    cv = cv_eval(X, y, ec, cfg.algorithm, run, n_repeats=1)
    lopo = []
    for held in (data if n_lopo else []):
        tr = [n for n in data if n != held]
        Xtr = pd.concat([data[n].X for n in tr], ignore_index=True)
        ytr = pd.concat([data[n].y for n in tr], ignore_index=True)
        fm = fit_model(Xtr, ytr, cfg.algorithm, cfg.params, cfg.seed, cfg.calibration, cfg.threshold_strategy)
        lopo.append({"held_out": held, "language": data[held].language, "train": tr,
                     "metrics": classification_metrics(data[held].y, fm.predict_proba(data[held].X), fm.threshold)})
        run.tick(f"hold out {held}")

    fm = fit_model(X, y, cfg.algorithm, cfg.params, cfg.seed, cfg.calibration, cfg.threshold_strategy)
    run.tick("final fit")
    perm = permutation_importance_cv(X, y, cfg.algorithm, cfg.params, cfg.seed, n_splits=cfg.n_splits)
    run.tick("permutation importance")
    stats = training_statistics(X, fm)
    blocking = fs.blocking_features(features)
    mid = f"{cfg.algorithm}-{cfg.feature_set.replace('_', '')}-{uuid.uuid4().hex[:6]}"
    limitations = list(next(iter(data.values())).limitations)
    if len(langs) > 1:
        limitations.append("Trained on a mix of C and C++ projects; the shared metrics were not shown to mean the same thing in both languages.")
    if len(data) == 1:
        limitations.append("Trained on a single project: no cross-project estimate of performance exists for this model.")
    limitations.append("Applying this model to uploaded code uses re-measured (approximate) features, not the original MDP tool's values.")
    manifest = {
        "id": mid, "name": cfg.name or f"{ALGORITHMS[cfg.algorithm]['label']} on {'+'.join(cfg.projects)}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "algorithm": cfg.algorithm,
        "algorithm_label": ALGORITHMS[cfg.algorithm]["label"], "hyperparameters": params, "seed": cfg.seed,
        "task": "module-level (function/method) binary defect proneness", "granularity": "function",
        "supported_languages": langs, "mixed_language_training": len(langs) > 1,
        "feature_set": cfg.feature_set, "features": features, "feature_definitions": [d for d in fs.schema_description() if d["name"] in features],
        "preprocessing": describe_preprocessing(cfg.algorithm),
        "applicable_to_uploaded_code": not blocking, "blocking_features": blocking,
        "training_datasets": [{"id": d.dataset_id, "version": d.version, "rows": d.n, "defect_rate": round(float(d.y.mean()), 4),
                               "sha256": d.provenance.get("sha256"), "language": d.language} for d in data.values()],
        "training_rows": int(len(y)), "training_defect_rate": round(float(y.mean()), 4),
        "calibration": cfg.calibration, "decision_threshold": fm.threshold, "threshold_strategy": cfg.threshold_strategy,
        "split_definition": f"StratifiedKFold(n_splits={cfg.n_splits}, shuffle=True, random_state={cfg.seed}); "
                            "imputer/scaler/calibrator/threshold fit on training folds only (inner 3-fold out-of-fold scores)",
        "evaluation": {"cross_validation": {"summary": cv["summary"], "note": "Pooled, stratified by label only (projects are mixed across folds)."},
                       "leave_one_project_out": lopo},
        "global_explanations": {"permutation_importance_heldout": perm, "intrinsic": intrinsic_importance(fm)},
        "training_statistics": stats, "limitations": limitations,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform(), "scikit_learn": sklearn.__version__,
                        "numpy": np.__version__, "pandas": pd.__version__},
    }
    d = _model_dir(mid)
    d.mkdir(parents=True, exist_ok=True)
    joblib.dump(fm, d / "model.joblib")
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def list_models() -> list[dict]:
    out = []
    for f in sorted(config.MODELS_DIR.glob("*/manifest.json"), reverse=True):
        m = json.loads(f.read_text())
        out.append({k: m[k] for k in ("id", "name", "created_at", "algorithm", "algorithm_label", "supported_languages", "feature_set",
                                      "applicable_to_uploaded_code", "blocking_features", "calibration", "decision_threshold",
                                      "training_rows", "training_defect_rate", "mixed_language_training")}
                   | {"n_features": len(m["features"]), "training_projects": [d["id"].split("/")[1] for d in m["training_datasets"]],
                      "cv_roc_auc": (m["evaluation"]["cross_validation"]["summary"].get("roc_auc") or {}).get("mean"),
                      "lopo_roc_auc": [r["metrics"]["roc_auc"] for r in m["evaluation"]["leave_one_project_out"]]})
    return out


def load_manifest(mid: str) -> dict:
    f = _model_dir(mid) / "manifest.json"
    if not f.exists():
        raise KeyError(mid)
    return json.loads(f.read_text())


def load_model(mid: str) -> FittedModel:
    f = _model_dir(mid) / "model.joblib"
    if not f.exists():
        raise KeyError(mid)
    return joblib.load(f)  # local, self-produced artefact only


def delete_model(mid: str) -> None:
    import shutil
    d = _model_dir(mid)
    if not d.exists():
        raise KeyError(mid)
    shutil.rmtree(d)
