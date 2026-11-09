"""Dataset, experiment, model and prediction endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import jobs
from ..analysis import runner
from ..datasets.registry import ADAPTERS, get_adapter
from ..evaluation import experiments as ex
from ..features import schemas as fs
from ..models import predict as pred
from ..models import store as mstore
from ..preprocessing.pipelines import ALGORITHMS, resolve_params
from ..projects import store as pstore

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ datasets
@router.get("/datasets")
def datasets():
    return [a.status() for a in ADAPTERS.values()]


@router.post("/datasets/{name}/fetch")
def fetch_dataset(name: str, force: bool = False):
    try:
        return get_adapter(name).fetch(force)
    except KeyError:
        raise HTTPException(404, "Unknown dataset")
    except Exception as e:  # network failures should be explained, not hidden
        raise HTTPException(502, f"Download failed: {e}. You can import the repository ZIP manually instead.")


@router.post("/datasets/{name}/import")
async def import_dataset(name: str, request: Request):
    form = await request.form(max_files=2)
    f = form.get("file")
    if f is None or not hasattr(f, "read"):
        raise HTTPException(400, "Provide the dataset ZIP in the 'file' field")
    try:
        return get_adapter(name).import_zip(await f.read(), source="manual import: " + (f.filename or "upload"))
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/datasets/{name}/profile")
def dataset_profile(name: str, project: str, version: Optional[str] = None):
    try:
        return get_adapter(name).profile(project, version)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/datasets/{name}/scatter")
def dataset_scatter(name: str, project: str, feature: str, version: Optional[str] = None):
    try:
        return get_adapter(name).scatter(project, version, feature)
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(404, str(e))


@router.get("/feature-schema")
def feature_schema():
    return {"features": fs.schema_description(), "groups": fs.GROUPS, "unavailable_groups": fs.UNAVAILABLE_GROUPS,
            "sets": {"mdp21": fs.feature_names("mdp21"), "mdp_extractable": fs.feature_names("mdp_extractable")}}


@router.get("/algorithms")
def algorithms():
    return {k: {"label": v["label"], "defaults": v["defaults"], "allowed": sorted(v["allowed"])} for k, v in ALGORITHMS.items()}


# ------------------------------------------------------------------ experiments
class ExperimentIn(BaseModel):
    kind: str
    projects: list[str] = ["CM1", "JM1", "KC1", "PC1"]
    version: str = "cleaned_DDprime"
    feature_set: str = "mdp21"
    algorithms: list[str] = ["dummy", "logistic", "tree", "forest", "gboost"]
    params: dict = {}
    seed: int = 42
    n_splits: int = 5
    n_repeats: int = 2
    threshold_strategy: str = "oof_mcc"
    calibration: str = "none"
    focus_algorithm: str = "forest"
    focus_project: str = "JM1"


@router.get("/experiment-kinds")
def kinds():
    return ex.KINDS


@router.post("/experiments")
def start_experiment(body: ExperimentIn):
    if body.kind not in ex.KINDS:
        raise HTTPException(400, f"Unknown experiment kind {body.kind!r}")
    for a in body.algorithms:
        if a not in ALGORITHMS:
            raise HTTPException(400, f"Unknown algorithm {a!r}")
        try:
            resolve_params(a, body.params.get(a))
        except ValueError as e:
            raise HTTPException(400, str(e))
    if not get_adapter("nasa_mdp").status()["present"]:
        raise HTTPException(409, "NASA MDP data has not been downloaded yet. Open Model lab → Datasets.")
    cfg = ex.ExperimentConfig(**body.model_dump())

    def work(job: jobs.Job) -> dict:
        def cb(frac, msg):
            job.progress, job.message = frac, msg
        doc = ex.run_experiment(cfg, cb, job.cancel_event)
        return {"experiment_id": doc["id"]}

    return jobs.submit("experiment", work).to_dict()


@router.get("/experiments")
def experiments():
    return ex.list_experiments()


@router.get("/experiments/{eid}")
def experiment(eid: str):
    try:
        return ex.load_experiment(eid)
    except KeyError:
        raise HTTPException(404, "Experiment not found")


# ------------------------------------------------------------------ models
class TrainIn(BaseModel):
    name: str = ""
    algorithm: str = "forest"
    params: dict = {}
    projects: list[str] = ["CM1", "JM1", "PC1"]
    version: str = "cleaned_DDprime"
    feature_set: str = "mdp_extractable"
    calibration: str = "sigmoid"
    threshold_strategy: str = "oof_mcc"
    seed: int = 42


@router.post("/models/train")
def train(body: TrainIn):
    if body.algorithm not in ALGORITHMS:
        raise HTTPException(400, "Unknown algorithm")
    try:
        resolve_params(body.algorithm, body.params)
        fs.feature_names(body.feature_set)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    if not get_adapter("nasa_mdp").status()["present"]:
        raise HTTPException(409, "NASA MDP data has not been downloaded yet. Open Model lab → Datasets.")
    cfg = mstore.TrainConfig(**body.model_dump())

    def work(job: jobs.Job) -> dict:
        def cb(frac, msg):
            job.progress, job.message = frac, msg
        return {"model_id": mstore.train_model(cfg, cb, job.cancel_event)["id"]}

    return jobs.submit("train", work).to_dict()


@router.get("/models")
def models():
    return mstore.list_models()


@router.get("/models/{mid}")
def model(mid: str):
    try:
        return mstore.load_manifest(mid)
    except KeyError:
        raise HTTPException(404, "Model not found")


@router.delete("/models/{mid}")
def delete_model(mid: str):
    try:
        mstore.delete_model(mid)
    except KeyError:
        raise HTTPException(404, "Model not found")
    return {"deleted": mid}


# ------------------------------------------------------------------ project predictions
def _analysis(pid: str) -> dict:
    try:
        pstore.load_meta(pid)
    except KeyError:
        raise HTTPException(404, "Project not found")
    try:
        return runner.load_analysis(pid)
    except FileNotFoundError:
        raise HTTPException(409, "Run an analysis for this project first")


@router.get("/projects/{pid}/model-compatibility")
def compatibility(pid: str):
    a = _analysis(pid)
    out = []
    for m in mstore.list_models():
        c = pred.check_compat(mstore.load_manifest(m["id"]), a.get("features"))
        out.append({"model": m, "compatibility": c})
    feats = a.get("features") or {}
    return {"analysis_id": a["analysis_id"], "models": out, "languages_covered": feats.get("languages_covered", []),
            "unsupported_languages": feats.get("unsupported_languages", {}), "functions_measured": len(feats.get("rows", []))}


class PredictIn(BaseModel):
    model_id: str


@router.post("/projects/{pid}/predict")
def predict(pid: str, body: PredictIn):
    a = _analysis(pid)
    try:
        return pred.predict_project(pid, a, body.model_id)
    except pred.IncompatibleModel as e:
        raise HTTPException(422, {"message": "Model is not compatible with this project", **e.detail})
    except KeyError:
        raise HTTPException(404, "Model not found")


@router.get("/projects/{pid}/predictions")
def predictions(pid: str, model_id: str):
    a = _analysis(pid)
    return pred.load_predictions(pid, a["analysis_id"], model_id)  # null when none exist yet


class ExplainIn(BaseModel):
    model_id: str
    entity_id: str


@router.post("/projects/{pid}/explain")
def explain(pid: str, body: ExplainIn):
    a = _analysis(pid)
    try:
        return pred.explain_entity(a, body.model_id, body.entity_id)
    except pred.IncompatibleModel as e:
        raise HTTPException(422, e.detail)
    except KeyError as e:
        raise HTTPException(404, str(e))
