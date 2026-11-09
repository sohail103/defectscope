"""Feature schema for the NASA MDP unified metrics, and how (whether) each can be measured on uploaded code.

extraction:
  approximate  measured by DefectScope's own tokeniser/parser; same idea as the MDP metric but not identical
  derived      computed from approximate primitives with a formula verified on the MDP data itself
  unavailable  cannot be measured faithfully from source by DefectScope; models using it must not be applied
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str                 # size | complexity | halstead
    description: str
    extraction: str            # approximate | derived | unavailable
    source: str = ""           # DefectScope metric (or formula) it is computed from
    caveat: str = ""


_T = "Tokenisation rules differ from the original MDP tool (DefectScope counts leaf tokens from the Tree-sitter parse)."
MDP_FEATURES: list[FeatureSpec] = [
    FeatureSpec("LOC_TOTAL", "size", "Total lines of the module", "approximate", "loc",
                "Physical lines spanned by the function, including signature and braces."),
    FeatureSpec("LOC_BLANK", "size", "Blank lines", "approximate", "blank_lines"),
    FeatureSpec("LOC_COMMENTS", "size", "Comment-only lines", "approximate", "comment_lines",
                "Lines that carry only a comment."),
    FeatureSpec("LOC_CODE_AND_COMMENT", "size", "Lines with both code and a comment", "approximate", "code_and_comment_lines"),
    FeatureSpec("LOC_EXECUTABLE", "size", "Executable lines", "approximate", "executable_lines",
                "Distinct lines starting an executable statement; the MDP tool's exact rule is undocumented."),
    FeatureSpec("CYCLOMATIC_COMPLEXITY", "complexity", "McCabe cyclomatic complexity v(g)", "approximate", "cyclomatic",
                "Counts if/loops/case/catch/ternary and short-circuit && ||; the MDP tool may count differently."),
    FeatureSpec("BRANCH_COUNT", "complexity", "Branch count", "unavailable", "",
                "Tool-specific. In KC1 it equals 2·v(g)−1 in ~97% of rows, so it is nearly redundant with v(g); deliberately not emulated."),
    FeatureSpec("DESIGN_COMPLEXITY", "complexity", "McCabe design complexity iv(g)", "unavailable", "",
                "Requires reducing the module's call graph; not implemented."),
    FeatureSpec("ESSENTIAL_COMPLEXITY", "complexity", "McCabe essential complexity ev(g)", "unavailable", "",
                "Requires structured-programming reduction of the control-flow graph; not implemented."),
    FeatureSpec("NUM_OPERATORS", "halstead", "Total operators (N1)", "approximate", "halstead_N1", _T),
    FeatureSpec("NUM_OPERANDS", "halstead", "Total operands (N2)", "approximate", "halstead_N2", _T),
    FeatureSpec("NUM_UNIQUE_OPERATORS", "halstead", "Distinct operators (n1)", "approximate", "halstead_n1", _T),
    FeatureSpec("NUM_UNIQUE_OPERANDS", "halstead", "Distinct operands (n2)", "approximate", "halstead_n2", _T),
    FeatureSpec("HALSTEAD_LENGTH", "halstead", "N = N1 + N2", "derived", "N1 + N2"),
    FeatureSpec("HALSTEAD_VOLUME", "halstead", "V = N·log2(n1+n2)", "derived", "halstead_volume"),
    FeatureSpec("HALSTEAD_DIFFICULTY", "halstead", "D = (n1/2)·(N2/n2)", "derived", "halstead_difficulty"),
    FeatureSpec("HALSTEAD_LEVEL", "halstead", "L = 1/D", "derived", "halstead_level"),
    FeatureSpec("HALSTEAD_EFFORT", "halstead", "E = D·V", "derived", "halstead_effort"),
    FeatureSpec("HALSTEAD_CONTENT", "halstead", "I = V/D", "derived", "halstead_volume / halstead_difficulty"),
    FeatureSpec("HALSTEAD_PROG_TIME", "halstead", "T = E/18", "derived", "halstead_time"),
    FeatureSpec("HALSTEAD_ERROR_EST", "halstead", "B = V/3000", "derived", "halstead_bugs"),
]
BY_NAME = {f.name: f for f in MDP_FEATURES}
GROUPS = ["size", "complexity", "halstead"]
# Groups requested by the research brief that do not exist in the shared NASA schema.
UNAVAILABLE_GROUPS = {
    "coupling": "No coupling metrics are common to all four NASA projects.",
    "historical": "NASA MDP contains no development-history data. Needs a dataset with version history.",
}


def feature_names(which: str) -> list[str]:
    """Named feature sets. `mdp_extractable` is what can be re-measured on uploaded code."""
    if which == "mdp21":
        return [f.name for f in MDP_FEATURES]
    if which == "mdp_extractable":
        return [f.name for f in MDP_FEATURES if f.extraction != "unavailable"]
    raise KeyError(f"Unknown feature set {which!r}")


def group_of(name: str) -> str:
    return BY_NAME[name].group


def schema_description() -> list[dict]:
    return [asdict(f) for f in MDP_FEATURES]


def blocking_features(required: list[str]) -> list[str]:
    return [n for n in required if BY_NAME[n].extraction == "unavailable"]
