from __future__ import annotations

from .base import DatasetAdapter
from .nasa import NASAMDPAdapter

ADAPTERS: dict[str, DatasetAdapter] = {"nasa_mdp": NASAMDPAdapter()}


def get_adapter(name: str) -> DatasetAdapter:
    try:
        return ADAPTERS[name]
    except KeyError:
        raise KeyError(f"Unknown dataset adapter: {name}")
