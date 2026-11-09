"""Re-measure NASA-MDP-style features on analysed source (C/C++ functions only)."""
from __future__ import annotations

from ..core.schemas import Entity
from .schemas import BY_NAME, MDP_FEATURES

SUPPORTED_LANGUAGES = {"c", "cpp"}


def _value(name: str, m: dict) -> float | None:
    f = BY_NAME[name]
    if f.extraction == "unavailable":
        return None
    src = f.source
    if name == "HALSTEAD_LENGTH":
        return m["halstead_N1"] + m["halstead_N2"]
    if name == "HALSTEAD_CONTENT":
        d = m["halstead_difficulty"]
        return round(m["halstead_volume"] / d, 4) if d else 0.0
    return float(m[src])


def extract_rows(entities: list[Entity]) -> dict:
    """Build the feature table for every C/C++ function. Python functions are listed as unsupported:
    the NASA datasets contain no Python data, so no model trained on them applies."""
    rows, unsupported = [], {}
    for e in entities:
        if e.kind != "function":
            continue
        if e.language not in SUPPORTED_LANGUAGES:
            unsupported[e.language] = unsupported.get(e.language, 0) + 1
            continue
        values = {}
        for f in MDP_FEATURES:
            v = _value(f.name, e.metrics)
            if v is not None:
                values[f.name] = v
        rows.append({"entity_id": e.id, "path": e.path, "name": e.qualified_name, "language": e.language,
                     "start_line": e.range.start_line, "values": values})
    return {
        "schema_id": "nasa_mdp_unified21", "granularity": "function (module)",
        "available_features": [f.name for f in MDP_FEATURES if f.extraction != "unavailable"],
        "unavailable_features": [f.name for f in MDP_FEATURES if f.extraction == "unavailable"],
        "status": {f.name: {"extraction": f.extraction, "source": f.source, "caveat": f.caveat} for f in MDP_FEATURES},
        "languages_covered": sorted({r["language"] for r in rows}),
        "unsupported_languages": unsupported,
        "rows": rows,
    }
