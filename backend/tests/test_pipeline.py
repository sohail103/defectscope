import io
import zipfile

import pytest

from app.analysis.runner import load_analysis, run_analysis
from app.core.schemas import AnalysisConfig
from app.projects import extract, store


def _analyse(sample_zip):
    meta = store.create_from_zip("sample", sample_zip)
    run_analysis(meta.id, AnalysisConfig())
    return meta, load_analysis(meta.id)


def test_known_metrics(sample_zip):
    _, a = _analyse(sample_zip)
    fn = {e["qualified_name"]: e["metrics"] for e in a["entities"] if e["kind"] == "function"}
    # values verified by hand against pylib/inventory.py, native/util.c, native/shapes.cpp
    assert fn["Inventory.report"]["cyclomatic"] == 13
    assert fn["Inventory.report"]["nesting_depth"] == 6
    assert fn["Inventory.report"]["cognitive"] == 28
    assert fn["Inventory.report"]["parameters"] == 6  # `self` excluded
    assert fn["clamp"]["cyclomatic"] == 3
    assert fn["copy_buf"]["cyclomatic"] == 5  # while, &&, case 1, case 2 (default not counted)
    assert fn["Circle::grow"]["cyclomatic"] == 5  # if, &&, else-if, ||
    assert fn["Circle::area"]["cyclomatic"] == 2  # catch


def test_classes_and_oo(sample_zip):
    _, a = _analyse(sample_zip)
    cls = {e["name"]: e["metrics"] for e in a["entities"] if e["kind"] == "class"}
    assert cls["Circle"]["dit"] == 1 and cls["Shape"]["noc"] == 1
    assert cls["Circle"]["wmc"] == 7
    assert cls["Item"]["field_count"] == 2


def test_dependency_cycle_and_source_ranges(sample_zip):
    _, a = _analyse(sample_zip)
    assert ["pylib/inventory.py", "pylib/pricing.py"] in a["dependency_graph"]["cycles"]
    rep = next(e for e in a["entities"] if e["qualified_name"] == "Inventory.report")
    assert (rep["range"]["start_line"], rep["range"]["end_line"]) == (36, 53)
    assert {h["rule"] for h in a["hotspots"] if h["entity_id"] == rep["id"]} >= {"deep_nesting"}
    assert all(h["layer"] == "structural" for h in a["hotspots"])


def test_zip_path_traversal_rejected(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.py", "print(1)")
    buf.seek(0)
    with pytest.raises(extract.ExtractionError):
        extract.extract_zip(buf, tmp_path / "out")
    assert not (tmp_path / "evil.py").exists()


def test_api_flow(sample_zip):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/projects/upload-zip", files={"file": ("s.zip", sample_zip, "application/zip")})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    job = c.post(f"/api/projects/{pid}/analyze").json()
    import time
    for _ in range(100):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    assert c.get(f"/api/projects/{pid}/analysis").json()["summary"]["totals"]["functions"] == 16
    assert c.get(f"/api/projects/{pid}/tree").json()["children"]
    assert c.delete(f"/api/projects/{pid}").status_code == 200
