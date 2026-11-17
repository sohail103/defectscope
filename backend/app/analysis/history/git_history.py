"""Git history extraction (file-level) using GitPython.

Design notes
  * Only information up to the reference date is used (`HistoryConfig.until` or the newest commit), so
    values can be reproduced as of a past prediction point and never include "future" commits.
  * Attribution uncertainty is kept, not hidden: merges are skipped, renames are not followed, and
    changes are attributed to files, never to individual functions.
  * "Bug-fix" commits are a keyword heuristic on commit messages, not confirmed defect fixes.
  * Git is run with global/system config disabled, hooks disabled and fsmonitor off, because an uploaded
    repository's own .git/config is untrusted.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ...core.schemas import HistoryConfig

SAFE_GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.quotepath=false",
            "-c", "protocol.allow=never"]
_SEP = "\x1f"
NOTES = [
    "Merge commits are excluded and renames are not followed: a renamed file's history starts at the rename.",
    "\"Bug-fix\" commits are identified by keywords in commit messages. This is a heuristic, not confirmed defect data.",
    "History is file-level. Changes are not attributed to individual functions or lines.",
]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def open_repo(root: Path):
    """Return a GitPython Repo for the project, or (None, reason)."""
    if not (root / ".git").exists():
        return None, "No .git directory in the imported project"
    try:
        import git
        repo = git.Repo(root)
        repo.git.update_environment(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
        _ = repo.head.commit  # raises if the repository has no commits
        return repo, None
    except Exception as e:  # noqa: BLE001
        return None, f"Not a usable Git repository ({type(e).__name__})"


def _fix_regex(keywords: list[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")", re.IGNORECASE)


def extract_history(repo, cfg: HistoryConfig, paths: set[str]) -> dict:
    args = SAFE_GIT + ["log", "--no-merges", "--no-renames", "--numstat", f"--max-count={cfg.max_commits}",
                       f"--format=@@%H{_SEP}%an{_SEP}%ae{_SEP}%at{_SEP}%s"]
    if cfg.until:
        args.append(f"--until={cfg.until}")
    raw = repo.git.execute(args, stdout_as_string=True)
    fix_re = _fix_regex(cfg.bugfix_keywords)

    commits: list[dict] = []
    cur = None
    for line in raw.splitlines():
        if line.startswith("@@"):
            sha, name, email, ts, subject = (line[2:].split(_SEP) + [""] * 5)[:5]
            cur = {"sha": sha, "name": name, "email": email.lower(), "ts": float(ts or 0), "subject": subject, "files": {}}
            commits.append(cur)
        elif line.strip() and cur is not None:
            parts = line.split("\t")
            if len(parts) == 3:
                a, d, path = parts
                cur["files"][path] = (0 if a == "-" else int(a), 0 if d == "-" else int(d))  # binary files count as 0
    if not commits:
        return {"available": False, "reason": "The repository has no commits in the selected range"}

    ref_ts = max(c["ts"] for c in commits)
    if cfg.until:
        try:
            ref_ts = min(ref_ts, datetime.fromisoformat(cfg.until).replace(tzinfo=timezone.utc).timestamp() + 86400)
        except ValueError:
            pass

    files: dict[str, dict] = defaultdict(lambda: {"commits": 0, "authors": Counter(), "added": 0, "deleted": 0, "first": 1e18,
                                                  "last": 0.0, "fix": 0, "entropy": 0.0, "recent": 0})
    monthly: dict[str, dict] = defaultdict(lambda: {"commits": 0, "churn": 0, "fix_commits": 0, "authors": set()})
    contributors: dict[str, dict] = defaultdict(lambda: {"name": "", "commits": 0, "churn": 0})
    for c in commits:
        churn = {p: a + d for p, (a, d) in c["files"].items()}
        total = sum(churn.values())
        h = -sum((v / total) * math.log2(v / total) for v in churn.values() if v) if total and len(churn) > 1 else 0.0
        is_fix = bool(fix_re.search(c["subject"]))
        m = monthly[datetime.fromtimestamp(c["ts"], tz=timezone.utc).strftime("%Y-%m")]
        m["commits"] += 1; m["churn"] += total; m["fix_commits"] += is_fix; m["authors"].add(c["email"])
        ct = contributors[c["email"]]
        ct["name"] = ct["name"] or c["name"]; ct["commits"] += 1; ct["churn"] += total
        for p, (a, d) in c["files"].items():
            if p not in paths:
                continue
            f = files[p]
            f["commits"] += 1; f["added"] += a; f["deleted"] += d; f["authors"][c["email"]] += 1
            f["first"] = min(f["first"], c["ts"]); f["last"] = max(f["last"], c["ts"]); f["fix"] += is_fix; f["entropy"] += h
            f["recent"] += (ref_ts - c["ts"]) <= 90 * 86400

    out_files = {}
    for p, f in files.items():
        n = f["commits"]
        out_files[p] = {
            "git_commits": n, "git_authors": len(f["authors"]), "git_added": f["added"], "git_deleted": f["deleted"],
            "git_churn": f["added"] + f["deleted"], "git_fix_commits": f["fix"],
            "git_fix_ratio": round(f["fix"] / n, 3), "git_change_entropy": round(f["entropy"] / n, 3),
            "git_days_since_last_change": round((ref_ts - f["last"]) / 86400, 1), "git_age_days": round((ref_ts - f["first"]) / 86400, 1),
            "git_top_author_share": round(max(f["authors"].values()) / n, 3), "git_recent_commits_90d": f["recent"],
            "first_commit": _iso(f["first"]), "last_commit": _iso(f["last"]),
        }
    ordered = sorted(commits, key=lambda c: c["ts"])
    k = max(2, min(cfg.complexity_samples, len(ordered)))
    idx = sorted({round(i * (len(ordered) - 1) / (k - 1)) for i in range(k)}) if len(ordered) > 1 else [0]
    notes = list(NOTES)
    truncated = len(commits) >= cfg.max_commits
    if truncated:
        notes.append(f"Only the newest {cfg.max_commits} commits were read; older history is not included.")
    if (Path(repo.git_dir) / "shallow").exists():
        notes.append("The repository is a shallow clone, so history is incomplete.")
    return {
        "available": True, "head": repo.head.commit.hexsha[:10], "commits_analysed": len(commits), "truncated": truncated,
        "first_commit": _iso(ordered[0]["ts"]), "last_commit": _iso(ordered[-1]["ts"]), "reference_date": _iso(ref_ts),
        "until": cfg.until, "files": out_files,
        "monthly": [{"month": k, "commits": v["commits"], "churn": v["churn"], "fix_commits": v["fix_commits"], "authors": len(v["authors"])}
                    for k, v in sorted(monthly.items())],
        "contributors": sorted(({"email": e, **v} for e, v in contributors.items()), key=lambda r: -r["commits"])[:15],
        "authors_total": len(contributors), "fix_commits_total": sum(m["fix_commits"] for m in monthly.values()),
        "sample_commits": [{"sha": ordered[i]["sha"], "date": _iso(ordered[i]["ts"]), "subject": ordered[i]["subject"][:80]} for i in idx],
        "bugfix_keywords": cfg.bugfix_keywords, "notes": notes,
    }
