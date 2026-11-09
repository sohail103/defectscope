"""Tests for the ML pieces. They use synthetic data so they run offline and quickly;
the NASA-specific test is skipped when the dataset has not been downloaded."""
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from app.datasets.nasa import RAW_DIR, parse_arff
from app.evaluation.metrics import classification_metrics, reliability
from app.explainability.explain import local_explanation, training_statistics
from app.features import schemas as fs
from app.models import predict as pred
from app.models.fitting import Calibrator, best_threshold, fit_model
from app.preprocessing.pipelines import build_pipeline


def synthetic(n=600, seed=0):
    rng = np.random.default_rng(seed)
    loc = rng.lognormal(3, 1, n)
    cc = np.maximum(1, loc / 8 + rng.normal(0, 1, n))
    noise = rng.normal(size=n)
    p = 1 / (1 + np.exp(-2.5 * (np.log(loc) - 3.4)))  # strong, known signal in LOC
    y = rng.binomial(1, p)
    return pd.DataFrame({"LOC_TOTAL": loc, "CYCLOMATIC_COMPLEXITY": cc, "NOISE": np.abs(noise)}), pd.Series(y)


def test_metrics_match_hand_computation():
    y = [1, 1, 0, 0, 0, 0]
    p = [0.9, 0.4, 0.6, 0.2, 0.1, 0.3]
    m = classification_metrics(y, p, 0.5)
    assert (m["tp"], m["fp"], m["tn"], m["fn"]) == (1, 1, 3, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["specificity"] == 0.75
    assert m["balanced_accuracy"] == pytest.approx(0.625)
    assert m["roc_auc"] == pytest.approx(roc_auc_score(y, p))
    assert m["mcc"] == pytest.approx((1 * 3 - 1 * 1) / np.sqrt(2 * 2 * 4 * 4))


def test_dummy_model_has_chance_auc_and_zero_mcc():
    X, y = synthetic()
    fm = fit_model(X, y, "dummy", None, 1)
    m = classification_metrics(y, fm.predict_proba(X), fm.threshold)
    assert m["roc_auc"] == 0.5 and m["mcc"] == 0.0


def test_scaler_is_fit_on_training_rows_only():
    X, y = synthetic()
    pipe = build_pipeline("logistic", None, 0)
    tr = X.iloc[:300]
    pipe.fit(tr, y.iloc[:300])
    mean_in_pipe = pipe.named_steps["scale"].mean_
    expected = np.log1p(tr.to_numpy()).mean(axis=0)
    assert np.allclose(mean_in_pipe, expected)  # test rows had no influence


def test_models_beat_dummy_on_signal():
    X, y = synthetic()
    tr, te = slice(0, 400), slice(400, None)
    for algo in ("logistic", "tree", "forest", "gboost"):
        fm = fit_model(X.iloc[tr], y.iloc[tr], algo, None, 3)
        assert roc_auc_score(y.iloc[te], fm.predict_proba(X.iloc[te])) > 0.7, algo


def test_calibration_improves_brier_on_distorted_scores():
    rng = np.random.default_rng(0)
    true_p = rng.uniform(0, 1, 4000)
    y = rng.binomial(1, true_p)
    distorted = true_p ** 3  # monotone but badly calibrated
    for method in ("sigmoid", "isotonic"):
        cal = Calibrator(method).fit(distorted[:2000], y[:2000])
        before = np.mean((distorted[2000:] - y[2000:]) ** 2)
        after = np.mean((cal.transform(distorted[2000:]) - y[2000:]) ** 2)
        assert after < before
    assert reliability(y, true_p)["ece"] < 0.05  # well calibrated scores have low ECE


def test_threshold_chosen_from_training_scores_only():
    y = np.array([0] * 90 + [1] * 10)
    p = np.concatenate([np.linspace(0, 0.4, 90), np.linspace(0.3, 0.9, 10)])
    t = best_threshold(y, p)
    assert 0.2 < t < 0.9


def test_shap_local_accuracy_and_logistic_linear_decomposition():
    X, y = synthetic()
    for algo in ("logistic", "forest", "gboost"):
        fm = fit_model(X, y, algo, None, 3)
        st = training_statistics(X, fm)
        row = X.iloc[5].to_dict()
        e = local_explanation(fm, st, row)
        assert e["local_accuracy_error"] < 1e-6, algo
        assert e["contributions"][0]["feature"] in ("LOC_TOTAL", "CYCLOMATIC_COMPLEXITY", "NOISE")


def _manifest(features):
    return {"features": features, "supported_languages": ["c"],
            "feature_definitions": [{"name": f, "group": fs.group_of(f)} for f in features]}


def _features_doc(languages=("c",)):
    avail = fs.feature_names("mdp_extractable")
    return {"available_features": avail, "status": {n: {"extraction": fs.BY_NAME[n].extraction} for n in avail},
            "unsupported_languages": {}, "languages_covered": list(languages),
            "rows": [{"entity_id": "f", "language": l, "values": {}} for l in languages]}


def test_compat_blocks_unmeasurable_features_and_wrong_language():
    ok = pred.check_compat(_manifest(fs.feature_names("mdp_extractable")), _features_doc())
    assert ok["compatible"] and ok["predictable_rows"] == 1
    research = pred.check_compat(_manifest(fs.feature_names("mdp21")), _features_doc())
    assert not research["compatible"] and "DESIGN_COMPLEXITY" in research["summary"]
    wrong_lang = pred.check_compat(_manifest(fs.feature_names("mdp_extractable")), _features_doc(("cpp",)))
    assert not wrong_lang["compatible"] and wrong_lang["excluded_by_language"] == {"cpp": 1}
    assert not pred.check_compat(_manifest(["LOC_TOTAL"]), None)["compatible"]


def test_arff_parser_rejects_ragged_rows():
    good = "@relation x\n@attribute a numeric\n@attribute Defective {Y,N}\n@data\n1,Y\n2,N\n"
    assert list(parse_arff(good).columns) == ["a", "Defective"]
    with pytest.raises(ValueError):
        parse_arff("@attribute a numeric\n@attribute b numeric\n@data\n1,2\n3\n")


@pytest.mark.skipif(not RAW_DIR.exists(), reason="NASA data not downloaded")
def test_nasa_cleaned_version_has_no_duplicates():
    from app.datasets.registry import get_adapter
    p = get_adapter("nasa_mdp").profile("KC1", "cleaned_DDprime")
    assert p["duplicate_feature_rows"] == 0 and p["rows"] == 1162 and p["n_features"] == 21
