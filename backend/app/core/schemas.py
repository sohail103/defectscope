"""Structured data models shared by passes, persistence and the API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Language = Literal["python", "c", "cpp"]
EntityKind = Literal["file", "class", "function"]
Layer = Literal["structural", "static_analysis", "predicted_risk", "historical"]
Severity = Literal["info", "warning", "high"]


class SourceRange(BaseModel):
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    start_col: int = 0  # 0-based byte offset within the line
    end_col: int = 0


class Entity(BaseModel):
    """Any analysed code entity. Granularity == kind."""

    id: str
    kind: EntityKind
    name: str
    qualified_name: str
    language: Language
    path: str
    range: SourceRange
    parent_id: Optional[str] = None
    parent_scope: Optional[str] = None
    metrics: dict[str, float] = Field(default_factory=dict)
    # Free-form explanatory detail (e.g. contributors to complexity).
    details: dict = Field(default_factory=dict)


class Hotspot(BaseModel):
    """A flagged region. `layer` keeps structural / static-analysis / predicted-risk
    findings separate so the UI never conflates them."""

    id: str
    layer: Layer = "structural"
    entity_id: str
    granularity: EntityKind
    path: str
    range: SourceRange
    rule: str
    severity: Severity
    value: float
    threshold: float
    message: str


class ExclusionRules(BaseModel):
    dirs: list[str] = Field(
        default_factory=lambda: [
            ".git", ".hg", ".svn", "build", "dist", "target", "node_modules",
            "venv", ".venv", "env", ".tox", "__pycache__", ".mypy_cache",
            ".pytest_cache", "site-packages", "cmake-build-debug", "cmake-build-release",
        ]
    )
    vendored_dirs: list[str] = Field(
        default_factory=lambda: ["vendor", "third_party", "thirdparty", "extern", "external", "deps"]
    )
    exclude_vendored: bool = True
    exclude_generated: bool = True
    exclude_tests: bool = False
    extra_globs: list[str] = Field(default_factory=list)
    max_file_bytes: int = 1024 * 1024


class Thresholds(BaseModel):
    """Structural-indicator thresholds. These flag *complexity*, not defects."""

    cyclomatic_warning: int = 10
    cyclomatic_high: int = 20
    nesting_warning: int = 4
    nesting_high: int = 6
    function_sloc_warning: int = 60
    function_sloc_high: int = 120
    params_warning: int = 5
    params_high: int = 8
    class_methods_warning: int = 20
    class_sloc_warning: int = 400


class AnalysisConfig(BaseModel):
    exclusions: ExclusionRules = Field(default_factory=ExclusionRules)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    enabled_passes: Optional[list[str]] = None  # None => all applicable


class FileInfo(BaseModel):
    path: str
    language: Optional[Language] = None
    size: int
    role: Literal["source", "header", "test", "build", "config", "other"] = "other"
    excluded: bool = False
    exclusion_reason: Optional[str] = None


class PassResult(BaseModel):
    name: str
    status: Literal["pending", "running", "ok", "failed", "skipped", "cancelled"] = "pending"
    duration_s: float = 0.0
    message: str = ""
    warnings: list[str] = Field(default_factory=list)


class ProjectMeta(BaseModel):
    id: str
    name: str
    created_at: str
    source: Literal["zip", "directory", "snippet", "local_path"]
    snapshot_hash: str = ""
    file_count: int = 0
    total_bytes: int = 0
    summary: dict = Field(default_factory=dict)  # discovery summary
