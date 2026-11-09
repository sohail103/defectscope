"""Analysis-pass framework: passes declare what they need and produce; the manager wires them."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.schemas import AnalysisConfig


class AnalysisCancelled(Exception):
    pass


@dataclass
class PassContext:
    root: Path
    config: AnalysisConfig
    artifacts: dict[str, Any] = field(default_factory=dict)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    on_progress: Callable[[float, str], None] = lambda frac, msg: None
    warnings: list[str] = field(default_factory=list)  # reset per pass by the manager
    # entity_id -> metric name -> value. Passes add to this through add_metrics().
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)

    def get(self, name: str) -> Any:
        return self.artifacts[name]

    def put(self, name: str, value: Any) -> None:
        self.artifacts[name] = value

    def add_metrics(self, entity_id: str, values: dict[str, float]) -> None:
        self.metrics.setdefault(entity_id, {}).update(values)

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise AnalysisCancelled()

    def progress(self, frac: float, msg: str = "") -> None:
        self.check_cancel()
        self.on_progress(max(0.0, min(1.0, frac)), msg)

    def warn(self, msg: str) -> None:
        if len(self.warnings) < 200:
            self.warnings.append(msg)


class AnalysisPass(ABC):
    name: str = ""
    description: str = ""
    requires: tuple[str, ...] = ()  # artifact names consumed
    produces: tuple[str, ...] = ()  # artifact names produced
    languages: Optional[frozenset] = None  # None => language independent
    granularity: tuple[str, ...] = ()  # entity kinds this pass produces values for

    @abstractmethod
    def run(self, ctx: PassContext) -> str:
        """Execute the pass; return a short human-readable status message."""
