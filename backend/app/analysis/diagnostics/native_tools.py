"""C/C++ providers: cppcheck and clang-tidy (Clang Static Analyzer checks)."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

from ...core.schemas import Diagnostic
from .base import DiagnosticProvider, ProviderContext, chunks, make_diag, run_tool, to_relpath
from .categories import clang_category, cppcheck_category


class CppcheckProvider(DiagnosticProvider):
    name = "cppcheck"
    description = "cppcheck: null pointers, bounds, leaks, uninitialised values, suspicious conditions."
    languages = frozenset({"c", "cpp"})
    install_hint = "apt install cppcheck  (or brew install cppcheck)"

    def run(self, ctx: ProviderContext) -> list[Diagnostic]:
        exe, out = self.path(), []
        for batch in chunks([f.path for f in ctx.files], 100):
            r = run_tool([exe, "--enable=warning,style,performance,portability", "--xml", "--xml-version=2", "--quiet",
                          "--suppress=missingIncludeSystem", "--suppress=missingInclude", "--max-configs=4", "-j", "2", *batch],
                         ctx.root, ctx.config.timeout_s)
            if r.timed_out:
                ctx.notes.append("cppcheck timed out; results are partial")
                break
            try:
                root = ET.fromstring(r.stderr[r.stderr.index("<?xml"):])  # cppcheck writes its XML report to stderr
            except (ValueError, ET.ParseError):
                if r.stderr.strip():
                    ctx.notes.append("cppcheck output could not be parsed")
                continue
            for e in root.iter("error"):
                locs = e.findall("location")
                if not locs or e.get("severity") == "information":
                    continue
                loc = locs[0]
                path = to_relpath(ctx.root, loc.get("file", ""))
                if not path:
                    continue
                rule, cwe = e.get("id", "cppcheck"), (int(e.get("cwe")) if (e.get("cwe") or "").isdigit() else None)
                sev = {"error": "high", "warning": "warning"}.get(e.get("severity", ""), "info")
                out.append(make_diag("cppcheck", rule, sev, cppcheck_category(rule, cwe), path, int(loc.get("line", 1)),
                                     int(loc.get("column", 1)), None, None, e.get("msg", ""), cwe))
        ctx.notes.append("cppcheck analysed files without a build configuration: macros and include paths are not resolved")
        return out


_CT_LINE = re.compile(r"^(.+?):(\d+):(\d+): (warning|error): (.*?) \[([^\]]+)\]$")
CLANG_CHECKS = ("-*,clang-analyzer-core.*,clang-analyzer-unix.*,clang-analyzer-cplusplus.*,clang-analyzer-security.*,"
                "clang-analyzer-deadcode.*,bugprone-*,-bugprone-easily-swappable-parameters,-bugprone-reserved-identifier,"
                "cert-err*,cert-str*")


class ClangTidyProvider(DiagnosticProvider):
    name = "clang-tidy"
    description = "clang-tidy with Clang Static Analyzer checks. Semantic analysis: needs headers to resolve (best with compile_commands.json)."
    languages = frozenset({"c", "cpp"})
    default_enabled = False
    install_hint = "pip install clang-tidy  (or apt install clang-tidy)"
    MAX_FILES = 100

    def run(self, ctx: ProviderContext) -> list[Diagnostic]:
        exe, out, seen = self.path(), [], set()
        files = ctx.files[: self.MAX_FILES]
        if len(ctx.files) > self.MAX_FILES:
            ctx.notes.append(f"clang-tidy analysed the first {self.MAX_FILES} of {len(ctx.files)} files")
        deadline = time.monotonic() + ctx.config.timeout_s
        failed = 0
        for f in files:
            left = deadline - time.monotonic()
            if left <= 1:
                ctx.notes.append("clang-tidy ran out of time; results are partial")
                break
            if ctx.compile_commands_dir:
                args = [exe, "-p", str(ctx.compile_commands_dir), "--config={}", f"--checks={CLANG_CHECKS}", "--quiet", f.path]
            else:  # no build info: parse standalone with a generic standard; missing headers will limit the analysis
                lang = ["-x", "c++", "-std=c++17"] if f.language == "cpp" else ["-x", "c", "-std=c11"]
                args = [exe, "--config={}", f"--checks={CLANG_CHECKS}", "--quiet", f.path, "--", *lang]
            r = run_tool(args, ctx.root, int(min(60, left)))
            if r.timed_out:
                continue
            had_error = False
            for line in r.stdout.splitlines():
                m = _CT_LINE.match(line)
                if not m:
                    continue
                file, ln, col, level, msg, check = m.groups()
                if check == "clang-diagnostic-error" or (level == "error" and check.startswith("clang-diagnostic")):
                    had_error = True  # compile error (usually a missing header); not a code finding
                    continue
                path = to_relpath(ctx.root, file)
                key = (path, ln, col, check)
                if not path or key in seen:
                    continue
                seen.add(key)
                out.append(make_diag("clang-tidy", check, "warning", clang_category(check), path, int(ln), int(col), None, None, msg))
            failed += had_error
        if failed:
            ctx.notes.append(f"{failed} file(s) had compile errors (e.g. unresolved includes), so Clang's semantic analysis of them is incomplete"
                             + ("" if ctx.compile_commands_dir else "; providing compile_commands.json usually fixes this"))
        if ctx.compile_commands_dir:
            ctx.notes.append(f"used compile_commands.json from {ctx.compile_commands_dir.name or '.'}")
        return out
