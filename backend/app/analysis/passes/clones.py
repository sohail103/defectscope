"""Duplicate-code indicator: functions with an identical syntax-tree shape (Type-2 structural clones).

Identifiers and literals are ignored; only the sequence of named node types is compared. Two functions with the same
shape are *likely* copy-pasted variants but may also be legitimately similar (e.g. generated-style getters), so the
result is an indicator for review, and small functions are excluded.
"""
from __future__ import annotations

import hashlib

from ...core.schemas import Entity
from ..base import AnalysisPass, PassContext, PassSkipped
from .core import LANGS


class DuplicateCodePass(AnalysisPass):
    name = "duplicate_code"
    description = "Find functions with identical syntax-tree structure (renamed copies)."
    requires = ("entities", "entity_nodes", "basic_metrics")
    produces = ("clone_groups",)
    languages = LANGS
    granularity = ("function",)

    def run(self, ctx: PassContext) -> str:
        cfg = ctx.config.clones
        if not cfg.enabled:
            raise PassSkipped("Duplicate-code detection is disabled in the configuration")
        entities: list[Entity] = ctx.get("entities")
        nodes = ctx.get("entity_nodes")
        buckets: dict[tuple, list[tuple[Entity, int]]] = {}
        for e in entities:
            if e.kind != "function" or ctx.metrics.get(e.id, {}).get("sloc", 0) < cfg.min_function_sloc:
                continue
            types: list[str] = []
            stack = [nodes[e.id]]
            while stack:
                n = stack.pop()
                if n.is_named and n.type != "comment":
                    types.append(n.type)
                stack.extend(reversed(n.children))
            if len(types) < cfg.min_nodes:
                continue
            digest = hashlib.blake2b(",".join(types).encode(), digest_size=10).hexdigest()
            buckets.setdefault((e.language, digest), []).append((e, len(types)))
        groups = []
        for (lang, digest), members in buckets.items():
            if len(members) < 2:
                continue
            gid = f"clone-{digest[:8]}"
            groups.append({"id": gid, "language": lang, "size": len(members), "nodes": members[0][1],
                           "sloc": ctx.metrics[members[0][0].id].get("sloc", 0),
                           "members": [{"entity_id": m.id, "path": m.path, "name": m.qualified_name, "start_line": m.range.start_line}
                                       for m, _ in members]})
            for m, _ in members:
                ctx.add_metrics(m.id, {"clone_group_size": len(members)})
        groups.sort(key=lambda g: (-g["size"], -g["sloc"]))
        ctx.put("clone_groups", groups)
        return f"{len(groups)} group(s) of structurally identical functions"
