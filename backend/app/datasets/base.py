"""Dataset adapter interface. Adapters keep raw data, schema, labels and provenance explicit."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class LoadedDataset:
    """An in-memory dataset in DefectScope's internal representation."""

    dataset_id: str                 # e.g. "nasa_mdp/KC1"
    version: str                    # e.g. "cleaned_DD"
    X: pd.DataFrame                 # raw (untransformed) feature values
    y: pd.Series                    # 1 = defective, 0 = not defective (original label preserved in `label_map`)
    language: str                   # "c" | "cpp" | "python" | ...
    granularity: str                # unit the rows describe, e.g. "function/module"
    schema_id: str                  # identifies the feature definitions
    provenance: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    label_map: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.y)


class DatasetAdapter(ABC):
    name: str = ""
    description: str = ""
    task: str = ""

    @abstractmethod
    def status(self) -> dict:
        """Whether raw data is present, with provenance and per-dataset listing."""

    @abstractmethod
    def fetch(self, force: bool = False) -> dict:
        """Retrieve/import the raw data (never silently modifies existing raw files)."""

    @abstractmethod
    def load(self, project: str, version: Optional[str] = None) -> LoadedDataset:
        """Return one dataset in internal representation."""
