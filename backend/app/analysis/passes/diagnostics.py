"""Static-analysis pass: runs external tools through providers and maps findings onto code entities."""
from __future__ import annotations

import time
from collections import Counter

from ...core.schemas import Diagnostic, Entity, FileInfo
from ..base import AnalysisPass, PassContext, PassSkipped
from ..diagnostics.base import ProviderContext
from ..diagnostics.registry import PROVIDERS


class StaticAnalysisPass(AnalysisPass):
    name = "static_analysis"
    description = "Run deterministic static-analysis tools (Ruff, Bandit, Pylint, cppcheck, clang-tidy) and unify their findings."
    requires = ("files", "entities", "discovery_summary")
    produces = ("diagnostics", "tool_status", "diagnostics_summary")
    granularity = ("file", "class", "function")

    def run(self, ctx: PassContext) -> str:
        cfg = ctx.config.static_analysis
        if not cfg.enabled:
            raise PassSkipped("Static analysis is disabled in the configuration")
        files: list[FileInfo] = ctx.get("files")
        entities: list[Entity] = ctx.get("entities")
        summary = ctx.get("discovery_summary")
        cc = (summary.get("build_systems") or {}).get("compile_commands") or []
        cc_dir = (ctx.root / cc[0]).parent if cc else None

        diagnostics: list[Diagnostic] = []
        status: list[dict] = []
        for i, name in enumerate(cfg.tools):
            ctx.progress(i / max(1, len(cfg.tools)), name)
            prov = PROVIDERS.get(name)
            if prov is None:
                ctx.warn(f"Unknown static-analysis tool {name!r}")
                continue
            mine = [f for f in files if f.language in prov.languages]
            rec = {"tool": name, "available": prov.available(), "version": None, "ran": False, "files": len(mine),
                   "findings": 0, "duration_s": 0.0, "notes": [], "error": None}
            if not mine:
                rec["notes"].append("No files in a supported language")
            elif not rec["available"]:
                rec["notes"].append(f"Not installed. Install with: {prov.install_hint}")
            else:
                rec["version"] = prov.version()
                if len(mine) > cfg.max_files_per_tool:
                    rec["notes"].append(f"Limited to the first {cfg.max_files_per_tool} of {len(mine)} files")
                pctx = ProviderContext(ctx.root, mine[: cfg.max_files_per_tool], cfg, compile_commands_dir=cc_dir)
                t0 = time.perf_counter()
                try:
                    found = prov.run(pctx)
                    rec["ran"], rec["findings"] = True, len(found)
                    diagnostics.extend(found)
                except Exception as e:  # noqa: BLE001 - a broken tool must not break the analysis
                    rec["error"] = f"{type(e).__name__}: {e}"
                    ctx.warn(f"{name} failed: {rec['error']}")
                rec["duration_s"] = round(time.perf_counter() - t0, 2)
                rec["notes"].extend(pctx.notes)
            status.append(rec)

        # drop exact duplicates, then attach each finding to its innermost function/class
        uniq = {d.id: d for d in diagnostics}
        diagnostics = sorted(uniq.values(), key=lambda d: (d.path, d.range.start_line, d.tool, d.rule))
        by_file: dict[str, list[Entity]] = {}
        for e in entities:
            if e.kind != "file":
                by_file.setdefault(e.path, []).append(e)
        for lst in by_file.values():
            lst.sort(key=lambda e: e.range.end_line - e.range.start_line)  # smallest span first => innermost wins
        sev_rank = {"info": 1, "warning": 2, "high": 3}
        for d in diagnostics:
            for e in by_file.get(d.path, []):
                if e.range.start_line <= d.range.start_line <= e.range.end_line:
                    d.entity_id = e.id
                    break
        groups: dict[tuple, set] = {}
        for d in diagnostics:
            groups.setdefault((d.path, d.range.start_line, d.category), set()).add(d.tool)
        for d in diagnostics:  # agreement between independent tools is useful evidence of a real issue
            d.corroborated_by = sorted(groups[(d.path, d.range.start_line, d.category)] - {d.tool})
        per_entity: dict[str, Counter] = {}
        for d in diagnostics:
            for key in {d.entity_id, d.path}:
                if key:
                    c = per_entity.setdefault(key, Counter())
                    c["total"] += 1
                    c[d.severity] += 1
        for key, c in per_entity.items():
            ctx.add_metrics(key, {"diagnostics_total": c["total"], "diagnostics_high": c["high"], "diagnostics_warning": c["warning"]})

        ctx.put("diagnostics", diagnostics)
        ctx.put("tool_status", status)
        ctx.put("diagnostics_summary", {
            "total": len(diagnostics), "by_tool": dict(Counter(d.tool for d in diagnostics)),
            "by_severity": dict(Counter(d.severity for d in diagnostics)),
            "by_category": dict(Counter(d.category for d in diagnostics)),
            "top_rules": [{"tool": t, "rule": r, "count": n} for (t, r), n in Counter((d.tool, d.rule) for d in diagnostics).most_common(10)],
            "files_with_findings": len({d.path for d in diagnostics}),
        })
        ran = [s["tool"] for s in status if s["ran"]]
        missing = [s["tool"] for s in status if not s["available"] and s["files"]]
        msg = f"{len(diagnostics)} findings from {', '.join(ran) or 'no tools'}"
        if missing:
            ctx.warn("Not installed: " + ", ".join(missing))
            msg += f" ({', '.join(missing)} not installed)"
        return msg
