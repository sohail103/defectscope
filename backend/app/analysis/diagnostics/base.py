"""Static-analysis provider framework.

Providers wrap external tools and translate their output into the common `Diagnostic` model.
Safety rules for every provider:
  * the tool analyses files, it never builds or runs the project;
  * project-supplied tool configuration (pyproject.toml, .pylintrc, .clang-tidy ...) is ignored so that an
    uploaded repository cannot change what runs; DefectScope passes its own explicit settings;
  * subprocesses get a minimal environment, no shell, and a hard timeout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ...core.schemas import Diagnostic, FileInfo, StaticAnalysisConfig


@dataclass
class ProviderContext:
    root: Path
    files: list[FileInfo]                # analysable (non-excluded) files for this provider's languages
    config: StaticAnalysisConfig
    compile_commands_dir: Optional[Path] = None
    notes: list[str] = field(default_factory=list)  # provider-level limitations surfaced in the UI


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def find_tool(name: str) -> Optional[str]:
    """Locate a tool on PATH or next to the running interpreter (virtualenv bin)."""
    extra = str(Path(sys.executable).parent)
    return shutil.which(name, path=os.pathsep.join([extra, os.environ.get("PATH", "")]))


def run_tool(args: list[str], cwd: Path, timeout: int, extra_env: Optional[dict] = None) -> ToolResult:
    home = tempfile.mkdtemp(prefix="defectscope-tool-")
    env = {"PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")]), "HOME": home,
           "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "XDG_CACHE_HOME": home, **(extra_env or {})}
    try:
        p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, shell=False,
                           errors="replace")
        return ToolResult(p.returncode, p.stdout, p.stderr)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return ToolResult(-1, out, "", timed_out=True)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def chunks(items: list, n: int):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def to_relpath(root: Path, filename: str) -> Optional[str]:
    """Normalise a tool-reported path to a project-relative POSIX path (None if outside the project)."""
    p = Path(filename)
    p = p if p.is_absolute() else (root / p)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


class DiagnosticProvider(ABC):
    name: str = ""
    description: str = ""
    languages: frozenset = frozenset()
    default_enabled: bool = True
    install_hint: str = ""
    executable: str = ""

    def path(self) -> Optional[str]:
        return find_tool(self.executable or self.name)

    def available(self) -> bool:
        return self.path() is not None

    def version(self) -> Optional[str]:
        exe = self.path()
        if not exe:
            return None
        r = run_tool([exe, "--version"], Path(tempfile.gettempdir()), 20)
        lines = [l.strip() for l in (r.stdout or r.stderr).splitlines() if any(c.isdigit() for c in l)]
        return lines[0][:80] if lines else None

    @abstractmethod
    def run(self, ctx: ProviderContext) -> list[Diagnostic]:
        """Analyse ctx.files and return diagnostics (paths project-relative)."""


def make_diag(tool: str, rule: str, severity: str, category: str, path: str, line: int, col: int,
              end_line: Optional[int], end_col: Optional[int], message: str, cwe: Optional[int] = None) -> Diagnostic:
    from ...core.schemas import SourceRange
    line = max(1, int(line or 1))
    return Diagnostic(
        id=f"{tool}:{path}:{line}:{col}:{rule}", tool=tool, rule=rule, severity=severity, category=category,  # type: ignore[arg-type]
        path=path, message=message.strip()[:600], cwe=cwe,
        range=SourceRange(start_line=line, end_line=max(line, int(end_line or line)), start_col=max(0, int(col or 1) - 1),
                          end_col=max(0, int(end_col or col or 1) - 1)),
    )
