"""NASA MDP (Shepperd et al.) adapter, using the klainfo/NASADefectDataset mirror.

Facts established by inspecting the data (see docs/DATASETS.md):
  * Three versions are provided: OriginalData, and the cleaned D' / D'' versions of Shepperd et al. (2013).
  * The original data is heavily duplicated (e.g. 44% of KC1 rows have a feature-identical twin), which makes
    random train/test splits optimistic. D'' has no feature-identical duplicates.
  * Rows are anonymous modules (C functions / C++ methods) described only by precomputed metrics.
    No source code is included, so uploaded code can only be *re-measured*, not re-derived exactly.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..core import config
from ..projects.extract import safe_relpath
from .base import DatasetAdapter, LoadedDataset

SOURCE_URL = "https://codeload.github.com/klainfo/NASADefectDataset/zip/refs/heads/master"
RAW_DIR = config.DATASETS_RAW / "nasa_mdp"

# Public NASA MDP descriptions (Shepperd et al. 2013). KC1 is the only C++ project among the four used here.
PROJECTS = {
    "CM1": {"language": "c", "domain": "spacecraft instrument"},
    "JM1": {"language": "c", "domain": "real-time predictive ground system"},
    "KC1": {"language": "cpp", "domain": "storage management for ground data"},
    "PC1": {"language": "c", "domain": "flight software for an earth-orbiting satellite"},
}
VERSIONS = {
    "original": "OriginalData/MDP",
    "cleaned_Dprime": "CleanedData/MDP/D'",
    "cleaned_DDprime": "CleanedData/MDP/D''",
}
DEFAULT_VERSION = "cleaned_DDprime"
SCHEMA_ID = "nasa_mdp_unified21"

# The 21 metrics shared by all four projects (identical names in every version).
COMMON_FEATURES = [
    "LOC_BLANK", "BRANCH_COUNT", "LOC_CODE_AND_COMMENT", "LOC_COMMENTS", "CYCLOMATIC_COMPLEXITY",
    "DESIGN_COMPLEXITY", "ESSENTIAL_COMPLEXITY", "LOC_EXECUTABLE", "HALSTEAD_CONTENT", "HALSTEAD_DIFFICULTY",
    "HALSTEAD_EFFORT", "HALSTEAD_ERROR_EST", "HALSTEAD_LENGTH", "HALSTEAD_LEVEL", "HALSTEAD_PROG_TIME",
    "HALSTEAD_VOLUME", "NUM_OPERANDS", "NUM_OPERATORS", "NUM_UNIQUE_OPERANDS", "NUM_UNIQUE_OPERATORS", "LOC_TOTAL",
]

LIMITATIONS = [
    "Rows are anonymous modules described by precomputed metrics; no source code or history is included.",
    "Labels come from NASA's defect tracking at the module level and are not line-level.",
    "Four projects from one organisation; results may not transfer to other domains or languages.",
    "Original data contains many duplicate and some contradictory rows; prefer the cleaned versions.",
    "No coupling or development-history features exist in the shared schema.",
]


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_arff(text: str) -> pd.DataFrame:
    """Minimal ARFF reader for numeric attributes plus one nominal class column."""
    names: list[str] = []
    rows: list[list[str]] = []
    in_data = False
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("%"):
            continue
        low = s.lower()
        if low.startswith("@attribute"):
            parts = s.split(None, 2)
            names.append(parts[1].strip("'\""))
        elif low.startswith("@data"):
            in_data = True
        elif in_data:
            rows.append([c.strip() for c in s.split(",")])
    if not names or not rows:
        raise ValueError("ARFF file has no attributes or no data rows")
    bad = [i for i, r in enumerate(rows) if len(r) != len(names)]
    if bad:
        raise ValueError(f"{len(bad)} data row(s) have the wrong number of fields (first at data row {bad[0]})")
    return pd.DataFrame(rows, columns=names)


class NASAMDPAdapter(DatasetAdapter):
    name = "nasa_mdp"
    description = "NASA Metrics Data Program module-level defect datasets (CM1, JM1, KC1, PC1)."
    task = "module-level binary defect prediction"

    # ---- raw data management
    def _meta_file(self) -> Path:
        return config.DATASETS_META / "nasa_mdp.json"

    def status(self) -> dict:
        present = RAW_DIR.exists() and any(RAW_DIR.rglob("*.arff"))
        meta = json.loads(self._meta_file().read_text()) if self._meta_file().exists() else None
        return {
            "id": self.name, "description": self.description, "task": self.task, "present": present,
            "source": SOURCE_URL, "provenance": meta, "projects": PROJECTS, "versions": list(VERSIONS),
            "default_version": DEFAULT_VERSION, "schema_id": SCHEMA_ID, "common_features": COMMON_FEATURES,
            "limitations": LIMITATIONS,
        }

    def fetch(self, force: bool = False) -> dict:
        if RAW_DIR.exists() and any(RAW_DIR.rglob("*.arff")) and not force:
            return self.status()
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "DefectScope/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r:  # only a fixed, hard-coded URL is ever fetched
            blob = r.read(60 * config.MB)
        return self.import_zip(blob, source=SOURCE_URL)

    def import_zip(self, blob: bytes, source: str = "manual import") -> dict:
        """Install the dataset from a ZIP (downloaded or user supplied for offline use)."""
        zf = zipfile.ZipFile(io.BytesIO(blob))
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        files = {}
        wanted = {f"{d}/{p}.arff" for d in VERSIONS.values() for p in PROJECTS}
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".arff"):
                continue
            rel = safe_relpath(info.filename)
            rel = rel.split("/", 1)[1] if "/" in rel else rel  # drop the repo root directory
            if rel not in wanted:
                continue
            data = zf.read(info)
            dest = RAW_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            files[rel] = {"sha256": _sha256(data), "bytes": len(data)}
        if not files:
            raise ValueError("Archive contained none of the expected MDP .arff files")
        meta = {"source": source, "archive_sha256": _sha256(blob), "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "files": files}
        self._meta_file().write_text(json.dumps(meta, indent=2))
        return self.status()

    # ---- loading
    def _path(self, project: str, version: str) -> Path:
        if project not in PROJECTS:
            raise KeyError(f"Unknown project {project!r}")
        if version not in VERSIONS:
            raise KeyError(f"Unknown version {version!r}")
        p = RAW_DIR / VERSIONS[version] / f"{project}.arff"
        if not p.exists():
            raise FileNotFoundError(f"{p.name} not found. Download the dataset first.")
        return p

    def load(self, project: str, version: Optional[str] = None) -> LoadedDataset:
        version = version or DEFAULT_VERSION
        path = self._path(project, version)
        raw = path.read_bytes()
        df = parse_arff(raw.decode("utf-8", errors="replace"))
        label_col = df.columns[-1]
        y_raw = df[label_col].str.strip("'\"").str.upper()
        if not set(y_raw.unique()) <= {"Y", "N", "TRUE", "FALSE"}:
            raise ValueError(f"Unexpected class labels in {path.name}: {sorted(y_raw.unique())[:5]}")
        y = y_raw.isin(["Y", "TRUE"]).astype(int)
        X = df.drop(columns=[label_col]).replace("?", np.nan).apply(pd.to_numeric, errors="coerce")
        meta = self._meta_file()
        rel = f"{VERSIONS[version]}/{project}.arff"
        prov = json.loads(meta.read_text()) if meta.exists() else {}
        return LoadedDataset(
            dataset_id=f"{self.name}/{project}", version=version, X=X.astype(float), y=y.reset_index(drop=True),
            language=PROJECTS[project]["language"], granularity="module (function/method)", schema_id=SCHEMA_ID,
            provenance={"source": SOURCE_URL, "file": rel, "sha256": _sha256(raw),
                        "archive_sha256": prov.get("archive_sha256"), "retrieved_at": prov.get("retrieved_at"),
                        "domain": PROJECTS[project]["domain"], "class_column": label_col},
            limitations=LIMITATIONS, label_map={"Y": 1, "N": 0},
        )

    def common_schema_frame(self, project: str, version: Optional[str] = None) -> LoadedDataset:
        """Dataset restricted to the 21 metrics shared by every project."""
        ds = self.load(project, version)
        missing = [c for c in COMMON_FEATURES if c not in ds.X.columns]
        if missing:
            raise ValueError(f"{project}: missing common features {missing}")
        ds.X = ds.X[COMMON_FEATURES].copy()
        return ds

    # ---- profiling for the dataset explorer
    def profile(self, project: str, version: Optional[str] = None) -> dict:
        from scipy import stats

        ds = self.load(project, version)
        X, y = ds.X, ds.y
        feats = []
        pvals = []
        for c in X.columns:
            col = X[c]
            ok = col.notna()
            d1, d0 = col[ok & (y == 1)], col[ok & (y == 0)]
            const = col[ok].nunique() <= 1
            rho = p = auc = None
            if not const and len(d1) > 1 and len(d0) > 1:
                rho, _ = stats.spearmanr(col[ok], y[ok])
                u = stats.mannwhitneyu(d1, d0, alternative="two-sided")
                p, auc = float(u.pvalue), float(u.statistic / (len(d1) * len(d0)))
            q1, q3 = col.quantile(0.25), col.quantile(0.75)
            iqr = q3 - q1
            outl = int(((col < q1 - 1.5 * iqr) | (col > q3 + 1.5 * iqr)).sum()) if iqr > 0 else 0
            feats.append({
                "name": c, "missing": int(col.isna().sum()), "min": float(col.min()), "median": float(col.median()),
                "mean": float(col.mean()), "max": float(col.max()), "skew": float(col.skew()) if not const else 0.0,
                "constant": bool(const), "iqr_outliers": outl,
                "spearman_with_defect": None if rho is None or np.isnan(rho) else round(float(rho), 4),
                "mannwhitney_p": p, "auc_effect": None if auc is None else round(auc, 4),
                "median_defective": float(d1.median()) if len(d1) else None,
                "median_clean": float(d0.median()) if len(d0) else None,
            })
            pvals.append(p)
        # Benjamini-Hochberg adjustment over features that could be tested
        idx = [i for i, p in enumerate(pvals) if p is not None]
        order = sorted(idx, key=lambda i: pvals[i])
        m, prev = len(order), 1.0
        adj = {}
        for rank, i in reversed(list(enumerate(order, 1))):
            prev = min(prev, pvals[i] * m / rank)
            adj[i] = prev
        for i, f in enumerate(feats):
            f["p_adjusted_bh"] = adj.get(i)

        dup = int(X.duplicated().sum())
        conflict = int(X.duplicated(keep=False).sum() - pd.concat([X, y.rename("y")], axis=1).duplicated(keep=False).sum())
        corr = X.loc[:, [f["name"] for f in feats if not f["constant"]]].corr(method="spearman")
        pairs = []
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                v = corr.iloc[i, j]
                if abs(v) >= 0.9:
                    pairs.append({"a": cols[i], "b": cols[j], "spearman": round(float(v), 3)})
        pairs.sort(key=lambda r: -abs(r["spearman"]))
        branch_identity = None
        if {"BRANCH_COUNT", "CYCLOMATIC_COMPLEXITY"} <= set(X.columns):
            branch_identity = round(float((X.BRANCH_COUNT == 2 * X.CYCLOMATIC_COMPLEXITY - 1).mean()), 4)
        return {
            "dataset_id": ds.dataset_id, "version": ds.version, "language": ds.language, "granularity": ds.granularity,
            "rows": int(len(y)), "n_features": int(X.shape[1]), "defective": int(y.sum()),
            "defect_rate": round(float(y.mean()), 4), "imbalance_ratio": round(float((1 - y.mean()) / max(y.mean(), 1e-9)), 2),
            "missing_cells": int(X.isna().sum().sum()), "duplicate_feature_rows": dup,
            "duplicate_fraction": round(dup / len(y), 4), "conflicting_duplicate_rows": conflict,
            "features": feats, "high_correlation_pairs": pairs[:25], "branch_count_equals_2cc_minus_1": branch_identity,
            "provenance": ds.provenance, "limitations": ds.limitations,
        }

    def scatter(self, project: str, version: Optional[str], x: str, limit: int = 1500, bins: int = 10) -> dict:
        """Sample of (feature value, label) points plus defect rate per quantile bin of the feature."""
        ds = self.load(project, version)
        if x not in ds.X.columns:
            raise KeyError(f"Unknown feature {x!r}")
        col, y = ds.X[x], ds.y
        rng = np.random.default_rng(0)
        idx = rng.choice(len(y), size=min(limit, len(y)), replace=False)
        pts = [{"x": float(col.iloc[i]), "y": int(y.iloc[i])} for i in idx]
        try:
            q = pd.qcut(col, bins, duplicates="drop")
            rates = [{"range": str(iv), "n": int(len(g)), "defect_rate": float(y.loc[g.index].mean()), "median": float(g.median())}
                     for iv, g in col.groupby(q, observed=True)]
        except ValueError:
            rates = []
        rho, p = (stats_spearman(col, y))
        return {"feature": x, "points": pts, "bins": rates, "spearman": rho, "p": p, "n": int(len(y)),
                "note": "Defect rate per quantile bin shows association only; it does not show that the feature causes defects."}


def stats_spearman(col, y):
    from scipy import stats
    if col.nunique() <= 1:
        return None, None
    r = stats.spearmanr(col, y)
    return float(r.statistic), float(r.pvalue)
