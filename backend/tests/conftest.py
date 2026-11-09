import io
import os
import zipfile
from pathlib import Path

import pytest

# Isolate all state in a temp directory before the app modules read their config.
@pytest.fixture(autouse=True, scope="session")
def _home(tmp_path_factory):
    os.environ["DEFECTSCOPE_HOME"] = str(tmp_path_factory.mktemp("home"))
    import importlib
    from app.core import config
    importlib.reload(config)
    config.ensure_dirs()

@pytest.fixture
def sample_zip() -> io.BytesIO:
    root = Path(__file__).resolve().parents[2] / "examples" / "sample_project"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in root.rglob("*"):
            if p.is_file():
                z.write(p, "sample_project/" + p.relative_to(root).as_posix())
    buf.seek(0)
    return buf
