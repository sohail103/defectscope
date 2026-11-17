"""Python providers: Ruff (fast lint), Pylint (deeper, opt-in), Bandit (security)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ...core.schemas import Diagnostic
from .base import DiagnosticProvider, ProviderContext, chunks, make_diag, run_tool, to_relpath
from .categories import pylint_category, ruff_category, severity_from


class RuffProvider(DiagnosticProvider):
    name = "ruff"
    description = "Fast Python linter (pyflakes, bugbear, bandit-style and pylint-error rules)."
    languages = frozenset({"python"})
    install_hint = "pip install ruff"
    SELECT = "E4,E7,E9,F,B,S,PLE,PLW"

    def run(self, ctx: ProviderContext) -> list[Diagnostic]:
        exe, out = self.path(), []
        for batch in chunks([f.path for f in ctx.files], 200):
            r = run_tool([exe, "check", "--isolated", "--no-cache", "--output-format=json", "--exit-zero",
                          "--select", self.SELECT, "--ignore", "S101", *batch], ctx.root, ctx.config.timeout_s)
            if r.timed_out:
                ctx.notes.append("ruff timed out; results are partial")
                break
            try:
                items = json.loads(r.stdout or "[]")
            except json.JSONDecodeError:
                ctx.notes.append("ruff produced unreadable output")
                continue
            for it in items:
                path = to_relpath(ctx.root, it["filename"])
                if not path or not it.get("code"):
                    continue
                code = it["code"]
                sev = "high" if code.startswith(("E9", "F821", "F822")) else "info" if code.startswith(("F4", "F8")) else "warning"
                loc, end = it["location"], it.get("end_location") or {}
                out.append(make_diag("ruff", code, sev, ruff_category(code), path, loc["row"], loc["column"],
                                     end.get("row"), end.get("column"), it["message"]))
        return out


class PylintProvider(DiagnosticProvider):
    name = "pylint"
    description = "Pylint errors and warnings (slow on large projects; opt-in). Import resolution is disabled."
    languages = frozenset({"python"})
    default_enabled = False
    install_hint = "pip install pylint"

    def run(self, ctx: ProviderContext) -> list[Diagnostic]:
        exe, out = self.path(), []
        with tempfile.TemporaryDirectory() as td:
            rc = Path(td) / "empty.pylintrc"  # ignore any project-supplied config (it can load plugins)
            rc.write_text("[MASTER]\n")
            for batch in chunks([f.path for f in ctx.files], 100):
                r = run_tool([exe, f"--rcfile={rc}", "--disable=all", "--enable=E,W", "--disable=import-error,no-name-in-module,fixme",
                              "--output-format=json", "--persistent=n", "--score=n", "--jobs=1", *batch], ctx.root, ctx.config.timeout_s)
                if r.timed_out:
                    ctx.notes.append("pylint timed out; results are partial")
                    break
                try:
                    items = json.loads(r.stdout or "[]")
                except json.JSONDecodeError:
                    ctx.notes.append("pylint produced unreadable output")
                    continue
                for it in items:
                    path = to_relpath(ctx.root, it["path"])
                    if not path:
                        continue
                    sev = "high" if it["type"] in ("error", "fatal") else "warning" if it["type"] == "warning" else "info"
                    out.append(make_diag("pylint", it["symbol"], sev, pylint_category(it["symbol"], it["type"]), path, it["line"],
                                         (it.get("column") or 0) + 1, it.get("endLine"), (it.get("endColumn") or 0) + 1, it["message"]))
        ctx.notes.append("pylint ran without import resolution (project dependencies are not installed), so type-related results are limited")
        return out


class BanditProvider(DiagnosticProvider):
    name = "bandit"
    description = "Security-focused checks for Python code."
    languages = frozenset({"python"})
    install_hint = "pip install bandit"

    def run(self, ctx: ProviderContext) -> list[Diagnostic]:
        exe, out = self.path(), []
        for batch in chunks([f.path for f in ctx.files], 200):
            r = run_tool([exe, "-f", "json", "-q", "-s", "B101", *batch], ctx.root, ctx.config.timeout_s)
            if r.timed_out:
                ctx.notes.append("bandit timed out; results are partial")
                break
            try:
                data = json.loads(r.stdout or "{}")
            except json.JSONDecodeError:
                ctx.notes.append("bandit produced unreadable output")
                continue
            for it in data.get("results", []):
                path = to_relpath(ctx.root, it["filename"])
                if not path:
                    continue
                cwe = (it.get("issue_cwe") or {}).get("id")
                rng = it.get("line_range") or [it["line_number"]]
                out.append(make_diag("bandit", f"{it['test_id']} {it['test_name']}", severity_from(it["issue_severity"]), "security",
                                     path, it["line_number"], (it.get("col_offset") or 0) + 1, max(rng), None,
                                     f"{it['issue_text']} (confidence: {it['issue_confidence'].lower()})", cwe))
        return out
