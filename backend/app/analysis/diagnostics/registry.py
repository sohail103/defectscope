from __future__ import annotations

from .base import DiagnosticProvider
from .native_tools import ClangTidyProvider, CppcheckProvider
from .python_tools import BanditProvider, PylintProvider, RuffProvider

PROVIDERS: dict[str, DiagnosticProvider] = {p.name: p for p in (
    RuffProvider(), BanditProvider(), PylintProvider(), CppcheckProvider(), ClangTidyProvider())}


def tool_status() -> list[dict]:
    """Availability of every provider (shown in Analysis setup)."""
    return [{"name": p.name, "description": p.description, "languages": sorted(p.languages), "available": p.available(),
             "version": p.version() if p.available() else None, "default_enabled": p.default_enabled,
             "install_hint": p.install_hint} for p in PROVIDERS.values()]
