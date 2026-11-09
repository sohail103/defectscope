"""Central configuration. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("DEFECTSCOPE_HOME", Path(__file__).resolve().parents[3])).resolve()
WORKSPACES = ROOT / "workspaces"
DATASETS_RAW = ROOT / "datasets" / "raw"
DATASETS_PROCESSED = ROOT / "datasets" / "processed"
DATASETS_META = ROOT / "datasets" / "metadata"
MODELS_DIR = ROOT / "models"
EXPERIMENTS_DIR = ROOT / "experiments"

MB = 1024 * 1024


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# Upload / extraction limits (guard against zip bombs and huge repositories).
MAX_UPLOAD_BYTES = _int("DEFECTSCOPE_MAX_UPLOAD_MB", 200) * MB
MAX_EXTRACTED_BYTES = _int("DEFECTSCOPE_MAX_EXTRACTED_MB", 800) * MB
MAX_FILES = _int("DEFECTSCOPE_MAX_FILES", 50_000)
MAX_COMPRESSION_RATIO = _int("DEFECTSCOPE_MAX_RATIO", 200)

# Analysis limits.
MAX_ANALYSED_FILE_BYTES = _int("DEFECTSCOPE_MAX_SOURCE_FILE_KB", 1024) * 1024
MAX_ANALYSED_FILES = _int("DEFECTSCOPE_MAX_ANALYSED_FILES", 5000)

# Importing a directory that already exists on the machine is opt-in.
ALLOW_LOCAL_PATHS = os.environ.get("DEFECTSCOPE_ALLOW_LOCAL_PATHS", "0") == "1"

ANALYSIS_VERSION = "0.1.0"


def ensure_dirs() -> None:
    for p in (WORKSPACES, DATASETS_RAW, DATASETS_PROCESSED, DATASETS_META, MODELS_DIR, EXPERIMENTS_DIR):
        p.mkdir(parents=True, exist_ok=True)
