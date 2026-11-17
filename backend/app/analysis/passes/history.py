"""Git history passes (optional)."""
from __future__ import annotations

from ...core.schemas import Entity, FileInfo
from ..base import AnalysisPass, PassContext, PassSkipped
from ..history.git_history import extract_history, open_repo
from ..history.snapshots import measure_commit


class GitHistoryPass(AnalysisPass):
    name = "git_history"
    description = "File-level change history from Git: commits, churn, authors, entropy, recency, bug-fix-like commits."
    requires = ("files", "entities")
    produces = ("history",)
    granularity = ("file",)

    def run(self, ctx: PassContext) -> str:
        cfg = ctx.config.history
        if not cfg.enabled:
            raise PassSkipped("History analysis is disabled in the configuration")
        repo, why = open_repo(ctx.root)
        if repo is None:
            raise PassSkipped(why or "No repository")
        files: list[FileInfo] = ctx.get("files")
        ctx.progress(0.1, "reading git log")
        hist = extract_history(repo, cfg, {f.path for f in files})
        if not hist.get("available"):
            raise PassSkipped(hist.get("reason", "No history available"))
        entities: list[Entity] = ctx.get("entities")
        for e in entities:
            if e.kind == "file" and e.path in hist["files"]:
                ctx.add_metrics(e.id, {k: v for k, v in hist["files"][e.path].items() if isinstance(v, (int, float))})
        ctx.put("history", hist)
        n_files = len(hist["files"])
        if n_files < len(files):
            ctx.warn(f"{len(files) - n_files} analysed file(s) have no commits in the selected range (e.g. new, renamed or untracked)")
        return f"{hist['commits_analysed']} commits ({hist['first_commit']} to {hist['last_commit']}), {n_files} files with history"


class ComplexityHistoryPass(AnalysisPass):
    name = "complexity_history"
    description = "Complexity at evenly spaced past commits, read from Git objects (no checkout)."
    requires = ("history", "entities", "complexity_metrics")
    produces = ("complexity_history",)
    granularity = ("project", "file")

    def run(self, ctx: PassContext) -> str:
        hist = ctx.get("history")
        if not hist:
            raise PassSkipped("No history to sample")
        repo, _ = open_repo(ctx.root)
        entities: list[Entity] = ctx.get("entities")
        top = sorted((e for e in entities if e.kind == "file"), key=lambda e: -ctx.metrics.get(e.id, {}).get("max_cyclomatic", 0))[:5]
        track = {e.path for e in top}
        points = []
        samples = hist["sample_commits"]
        for i, s in enumerate(samples):
            ctx.progress(i / len(samples), s["date"])
            m = measure_commit(repo, s["sha"], ctx.config.exclusions, ctx.config.thresholds, track)
            points.append({"sha": s["sha"][:10], "date": s["date"], "subject": s["subject"], **m})
        if any(p["capped"] for p in points):
            ctx.warn("Some snapshots exceeded the file cap and were sampled (first files alphabetically)")
        ctx.put("complexity_history", {"points": points, "tracked_files": sorted(track),
                                       "note": "Measured with the same rules as the current analysis; files that fail to parse at old revisions are skipped."})
        return f"Complexity measured at {len(points)} commits"
