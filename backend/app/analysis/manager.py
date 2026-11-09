"""Central analysis manager: dependency resolution, progress, errors, cancellation."""
from __future__ import annotations

import time
import traceback
from typing import Callable

from ..core.schemas import PassResult
from .base import AnalysisCancelled, AnalysisPass, PassContext


class PassManager:
    def __init__(self, passes: list[AnalysisPass]):
        self.passes = {p.name: p for p in passes}
        self.producer: dict[str, str] = {}
        for p in passes:
            for art in p.produces:
                self.producer[art] = p.name

    def plan(self, enabled: list[str] | None = None) -> list[AnalysisPass]:
        """Topologically ordered passes, including transitive dependencies of `enabled`."""
        wanted = list(self.passes) if enabled is None else enabled
        for w in wanted:
            if w not in self.passes:
                raise ValueError(f"Unknown pass: {w}")
        order: list[str] = []
        state: dict[str, int] = {}

        def visit(name: str) -> None:
            if state.get(name) == 2:
                return
            if state.get(name) == 1:
                raise ValueError(f"Cyclic pass dependency at {name}")
            state[name] = 1
            for art in self.passes[name].requires:
                if art not in self.producer:
                    raise ValueError(f"No pass produces artifact '{art}' (needed by {name})")
                visit(self.producer[art])
            state[name] = 2
            order.append(name)

        for w in wanted:
            visit(w)
        return [self.passes[n] for n in order]

    def run(self, ctx: PassContext, enabled: list[str] | None = None,
            on_pass: Callable[[PassResult], None] = lambda r: None) -> list[PassResult]:
        plan = self.plan(enabled)
        results = [PassResult(name=p.name) for p in plan]
        for r in results:
            on_pass(r)
        n = len(plan)
        try:
            for i, (p, res) in enumerate(zip(plan, results)):
                ctx.check_cancel()
                missing = [a for a in p.requires if a not in ctx.artifacts]
                if missing:
                    res.status, res.message = "skipped", f"Missing inputs: {', '.join(missing)}"
                    on_pass(res)
                    continue
                res.status = "running"
                on_pass(res)
                ctx.warnings = []
                t0 = time.perf_counter()
                try:
                    res.message = p.run(ctx) or ""
                    res.status = "ok"
                    for art in p.produces:  # passes that only write per-entity metrics still "produce" their artifact
                        ctx.artifacts.setdefault(art, True)
                except AnalysisCancelled:
                    res.status = "cancelled"
                    raise
                except Exception as e:  # noqa: BLE001 - a failing pass must not kill the job
                    res.status = "failed"
                    res.message = f"{type(e).__name__}: {e}"
                    res.warnings.append(traceback.format_exc(limit=4))
                finally:
                    res.duration_s = round(time.perf_counter() - t0, 3)
                    res.warnings = (res.warnings + ctx.warnings)[:50]
                    on_pass(res)
        except AnalysisCancelled:
            for r in results:
                if r.status in ("pending", "running"):
                    r.status = "cancelled"
                    on_pass(r)
        return results
