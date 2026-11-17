#!/usr/bin/env python3
"""Build examples/demo_history_repo.zip: a small Git repository with a multi-author, multi-month history
whose final state is exactly examples/sample_project. Used by the 'sample with Git history' demo."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "examples" / "sample_project"
AUTHORS = {"alice": ("Alice Reed", "alice@example.com"), "bob": ("Bob Chen", "bob@example.com"), "carol": ("Carol Diaz", "carol@example.com")}


def final(rel: str) -> str:
    return (SRC / rel).read_text()


INV_V1 = '''"""Inventory management (sample code for DefectScope)."""


class Item:
    def __init__(self, sku, qty):
        self.sku = sku
        self.qty = qty


class Inventory:
    def __init__(self):
        self.items = {}

    def add(self, item):
        self.items[item.sku] = item
'''
INV_V2 = INV_V1.replace('"""Inventory', 'from . import pricing\n\n"""Inventory', 1) + '''
    def value(self):
        total = 0
        for sku, item in self.items.items():
            total += pricing.price_for(sku, item.qty)
        return total
'''
INV_V3 = INV_V2.replace("        self.items[item.sku] = item\n", "        if item.sku in self.items:\n            self.items[item.sku].qty += item.qty\n        else:\n            self.items[item.sku] = item\n")
INV_V4 = INV_V3 + '''
    def report(self, verbose):
        out = []
        for sku, item in self.items.items():
            if verbose:
                out.append((sku, item.qty))
            else:
                out.append(sku)
        return out
'''
PRICING_V1 = "def price_for(sku, qty):\n    return 10 * qty\n"
UTIL_V1 = '#include "util.h"\n\nint clamp(int v, int lo, int hi) {\n    if (v < lo) return lo;\n    return v;\n}\n'
UTIL_V2 = UTIL_V1.replace("    return v;\n", "    if (v > hi) return hi;\n    return v;\n")

# (date, author, message, {path: content})
HISTORY = [
    ("2026-01-12", "alice", "Initial inventory model", {"pylib/__init__.py": "", "pylib/inventory.py": INV_V1, "pylib/pricing.py": PRICING_V1}),
    ("2026-02-03", "bob", "Add clamp helper", {"native/util.h": final("native/util.h"), "native/util.c": UTIL_V1}),
    ("2026-02-20", "alice", "Add inventory valuation", {"pylib/inventory.py": INV_V2}),
    ("2026-03-09", "carol", "Fix crash when item already exists", {"pylib/inventory.py": INV_V3}),
    ("2026-03-25", "bob", "Fix clamp upper bound bug", {"native/util.c": UTIL_V2}),
    ("2026-04-14", "bob", "Add shapes", {"native/shapes.cpp": final("native/shapes.cpp")}),
    ("2026-05-05", "alice", "Add simple report", {"pylib/inventory.py": INV_V4}),
    ("2026-05-30", "alice", "Volume discount pricing", {"pylib/pricing.py": final("pylib/pricing.py")}),
    ("2026-06-18", "bob", "Add buffer copy helper", {"native/util.c": final("native/util.c")}),
    ("2026-07-07", "carol", "Fix memory handling in util", {"native/buggy.c": final("native/buggy.c")}),
    ("2026-08-19", "alice", "Add filters, formats and sorting to report", {"pylib/inventory.py": final("pylib/inventory.py")}),
    ("2026-09-02", "alice", "Fix report regression with empty filters", {"pylib/inventory.py": final("pylib/inventory.py") + "\n"}),
    ("2026-09-30", "carol", "Add legacy helpers and tests", {"pylib/legacy.py": final("pylib/legacy.py"), "tests/test_inventory.py": final("tests/test_inventory.py")}),
    ("2026-10-21", "alice", "Fix error in report output", {"pylib/inventory.py": final("pylib/inventory.py")}),
]


def git(repo: Path, *args, env=None):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env={**os.environ, **(env or {})})


def main() -> None:
    out = ROOT / "examples" / "demo_history_repo.zip"
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "demo_repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        for date, who, msg, files in HISTORY:
            for rel, content in files.items():
                p = repo / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            name, email = AUTHORS[who]
            stamp = f"{date}T12:00:00+0000"
            env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
                   "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
            git(repo, "add", "-A", env=env)
            git(repo, "commit", "-q", "-m", msg, env=env)
        shutil.rmtree(repo / ".git" / "hooks", ignore_errors=True)  # keep the archive small and hook-free
        cmp = subprocess.run(["diff", "-r", "-x", ".git", str(repo), str(SRC)], capture_output=True, text=True)
        assert cmp.returncode == 0, "final repository state must equal examples/sample_project:\n" + cmp.stdout
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(repo.rglob("*")):
                if p.is_file():
                    z.write(p, "demo_repo/" + p.relative_to(repo).as_posix())
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(HISTORY)} commits)")


if __name__ == "__main__":
    main()
