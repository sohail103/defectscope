from __future__ import annotations

from ...core.schemas import Entity
from ...features.extract import extract_rows
from ..base import AnalysisPass, PassContext


class FeatureExtractionPass(AnalysisPass):
    name = "feature_extraction"
    description = "Re-measure NASA-MDP-style module features (C/C++ functions) for model compatibility checks."
    requires = ("entities", "basic_metrics", "complexity_metrics", "halstead_metrics")
    produces = ("mdp_features",)
    languages = frozenset({"c", "cpp"})
    granularity = ("function",)

    def run(self, ctx: PassContext) -> str:
        entities: list[Entity] = ctx.get("entities")
        for e in entities:  # metrics are merged onto entities at the end of the run; do it here for extraction
            e.metrics = ctx.metrics.get(e.id, {})
        feats = extract_rows(entities)
        ctx.put("mdp_features", feats)
        n = len(feats["rows"])
        if feats["unsupported_languages"]:
            ctx.warn("No applicable feature schema for: " + ", ".join(f"{k} ({v} functions)" for k, v in feats["unsupported_languages"].items()))
        return f"{n} C/C++ functions measured on {len(feats['available_features'])} of 21 MDP features"
