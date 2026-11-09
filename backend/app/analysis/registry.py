from __future__ import annotations

from .manager import PassManager
from .passes.core import DiscoveryPass, ParsingPass, SymbolIndexPass
from .passes.features import FeatureExtractionPass
from .passes.metrics import BasicMetricsPass, ComplexityPass, HalsteadPass
from .passes.structure import (DependencyPass, OOMetricsPass, ProjectSummaryPass,
                               StructuralHotspotPass)


def default_manager() -> PassManager:
    return PassManager([
        DiscoveryPass(), ParsingPass(), SymbolIndexPass(), BasicMetricsPass(), ComplexityPass(),
        HalsteadPass(), DependencyPass(), OOMetricsPass(), StructuralHotspotPass(), FeatureExtractionPass(),
        ProjectSummaryPass(),
    ])


def describe_passes() -> list[dict]:
    m = default_manager()
    return [
        {"name": p.name, "description": p.description, "requires": list(p.requires),
         "produces": list(p.produces), "languages": sorted(p.languages) if p.languages else None,
         "granularity": list(p.granularity)}
        for p in m.plan()
    ]
