"""Structural passes: dependencies, object-oriented metrics, hotspots, project summary."""
from __future__ import annotations

import posixpath
from collections import Counter, defaultdict

from ...core.schemas import Entity, FileInfo, Hotspot
from ...parsers import treesitter as ts
from ..base import AnalysisPass, PassContext
from .core import LANGS


# ------------------------------------------------------------------ dependencies
def _py_imports(pf: ts.ParsedFile) -> list[tuple[str, list[str], int]]:
    """Returns (module, imported names, level) per import statement. level>0 => relative."""
    out = []
    stack = [pf.tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "import_statement":
            for c in n.named_children:
                nm = c.child_by_field_name("name") if c.type == "aliased_import" else c
                if nm is not None and nm.type == "dotted_name":
                    out.append((ts.text(nm), [], 0))
        elif n.type == "import_from_statement":
            mod = n.child_by_field_name("module_name")
            mtxt = ts.text(mod) if mod is not None else ""
            level = len(mtxt) - len(mtxt.lstrip("."))
            names = []
            for c in n.children_by_field_name("name"):
                nm = c.child_by_field_name("name") if c.type == "aliased_import" else c
                if nm is not None:
                    names.append(ts.text(nm))
            out.append((mtxt.lstrip("."), names, level))
        else:
            stack.extend(n.children)
    return out


def _c_includes(pf: ts.ParsedFile) -> list[tuple[str, bool]]:
    """(path, is_system) for each #include."""
    out = []
    stack = [pf.tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "preproc_include":
            p = n.child_by_field_name("path")
            if p is not None:
                raw = ts.text(p)
                out.append((raw.strip('<>"'), raw.startswith("<")))
        else:
            stack.extend(n.children)
    return out


class DependencyPass(AnalysisPass):
    name = "dependency_analysis"
    description = "File-level import/include graph with fan-in, fan-out, instability and cycles."
    requires = ("files", "parsed_files")
    produces = ("dependency_graph",)
    languages = LANGS
    granularity = ("file",)

    def run(self, ctx: PassContext) -> str:
        files: list[FileInfo] = ctx.get("files")
        parsed = ctx.get("parsed_files")
        paths = {f.path for f in files if f.path in parsed}
        py_mod: dict[str, str] = {}
        for p in paths:
            if p.endswith(".py"):
                dotted = p[:-3].replace("/", ".")
                if dotted.endswith(".__init__"):
                    dotted = dotted[: -len(".__init__")]
                parts = dotted.split(".")
                for i in range(len(parts)):  # register every suffix so src/ layouts resolve
                    py_mod.setdefault(".".join(parts[i:]), p)
                py_mod[dotted] = p
        by_basename: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            by_basename[posixpath.basename(p)].append(p)

        edges: set[tuple[str, str]] = set()
        external: dict[str, Counter] = defaultdict(Counter)
        for p in sorted(paths):
            pf = parsed[p]
            if pf.language == "python":
                for mod, names, level in _py_imports(pf):
                    targets: list[str] = []
                    if level:
                        base = posixpath.dirname(p)
                        for _ in range(level - 1):
                            base = posixpath.dirname(base)
                        prefix = (base.replace("/", ".") + ".") if base else ""
                        cands = [prefix + mod] if mod else []
                        cands += [prefix + (mod + "." if mod else "") + n for n in names]
                        targets = [py_mod[c] for c in cands if c in py_mod]
                    else:
                        cands = [mod] + [f"{mod}.{n}" for n in names]
                        targets = [py_mod[c] for c in cands if c in py_mod]
                        if not targets:
                            external[p][mod.split(".")[0]] += 1
                    for t in targets:
                        if t != p:
                            edges.add((p, t))
            else:
                for inc, system in _c_includes(pf):
                    tgt = None
                    if not system:
                        rel = posixpath.normpath(posixpath.join(posixpath.dirname(p), inc))
                        if rel in paths:
                            tgt = rel
                    if tgt is None:
                        suffix = [c for c in by_basename.get(posixpath.basename(inc), [])
                                  if c == inc or c.endswith("/" + inc)]
                        if len(suffix) >= 1:
                            tgt = sorted(suffix)[0]
                    if tgt and tgt != p:
                        edges.add((p, tgt))
                    elif tgt is None:
                        external[p][inc] += 1

        fan_out, fan_in = Counter(), Counter()
        for s, t in edges:
            fan_out[s] += 1
            fan_in[t] += 1
        cycles = _sccs(paths, edges)
        in_cycle = {n for c in cycles for n in c}
        ext_total: Counter = Counter()
        for p in paths:
            ext = external.get(p, Counter())
            ext_total.update(ext.keys())
            fo, fi = fan_out[p], fan_in[p]
            ctx.add_metrics(p, {
                "fan_in": fi, "fan_out": fo,
                "instability": round(fo / (fi + fo), 3) if (fi + fo) else 0.0,
                "external_dependencies": len(ext), "in_dependency_cycle": 1.0 if p in in_cycle else 0.0,
            })
        graph = {
            "nodes": [{"id": p, "language": parsed[p].language, "fan_in": fan_in[p], "fan_out": fan_out[p],
                       "in_cycle": p in in_cycle} for p in sorted(paths)],
            "edges": [{"source": s, "target": t} for s, t in sorted(edges)],
            "cycles": cycles,
            "external": dict(ext_total.most_common(40)),
            "note": "Resolved by path/module-name matching. Dynamic imports, include paths and conditional "
                    "includes are not resolved; unresolved ones are reported as external.",
        }
        ctx.put("dependency_graph", graph)
        return f"{len(edges)} internal dependencies, {len(cycles)} cycle group(s)"


def _sccs(nodes: set, edges: set) -> list[list[str]]:
    """Iterative Tarjan; returns strongly connected components with >1 node."""
    adj: dict[str, list[str]] = defaultdict(list)
    for s, t in edges:
        adj[s].append(t)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    st: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for root in sorted(nodes):
        if root in index:
            continue
        work = [(root, iter(adj[root]))]
        index[root] = low[root] = counter
        counter += 1
        st.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    st.append(w)
                    on.add(w)
                    work.append((w, iter(adj[w])))
                    advanced = True
                    break
                elif w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = st.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))
    return out


# ------------------------------------------------------------------ object-oriented metrics
class OOMetricsPass(AnalysisPass):
    name = "oo_metrics"
    description = "Chidamber-Kemerer suite (WMC, DIT, NOC, CBO, RFC, LCOM). CBO/RFC/LCOM are syntactic approximations."
    requires = ("entities", "entity_nodes", "complexity_metrics", "call_names", "basic_metrics")
    produces = ("oo_metrics",)
    languages = frozenset({"python", "cpp", "c"})
    granularity = ("class",)

    def run(self, ctx: PassContext) -> str:
        entities: list[Entity] = ctx.get("entities")
        nodes = ctx.get("entity_nodes")
        calls = ctx.get("call_names")
        classes = [e for e in entities if e.kind == "class"]
        funcs = [e for e in entities if e.kind == "function"]
        by_simple: dict[str, list[Entity]] = defaultdict(list)
        for c in classes:
            by_simple[c.name].append(c)
        ambiguous = sorted(n for n, v in by_simple.items() if len(v) > 1)
        if ambiguous:
            ctx.warn(f"Ambiguous class names resolved by name only: {', '.join(ambiguous[:8])}")
        methods_of: dict[str, list[Entity]] = defaultdict(list)
        for f in funcs:
            cid = f.details.get("class_entity_id")
            if cid:
                methods_of[cid].append(f)

        parents: dict[str, list[Entity]] = {}
        external_bases: dict[str, list[str]] = {}
        for c in classes:
            ps, ext = [], []
            for b in c.details.get("bases", []):
                hit = [x for x in by_simple.get(b, []) if x.id != c.id]
                (ps.append(hit[0]) if hit else ext.append(b))
            parents[c.id], external_bases[c.id] = ps, ext
        noc: Counter = Counter()
        for c in classes:
            for p in parents[c.id]:
                noc[p.id] += 1

        def dit(cid: str, seen: frozenset = frozenset()) -> int:
            if cid in seen:
                return 0
            ps = parents.get(cid, [])
            return 1 + max((dit(p.id, seen | {cid}) for p in ps), default=0) if ps else 0

        names = set(by_simple)
        for i, c in enumerate(classes):
            ctx.progress(i / max(1, len(classes)), c.qualified_name)
            ms = methods_of.get(c.id, [])
            wmc = sum(ctx.metrics[m.id].get("cyclomatic", 0) for m in ms)
            called = set().union(*[calls.get(m.id, set()) for m in ms]) if ms else set()
            rfc = len(ms) + len(called)
            fields = set(c.details.get("fields", []))
            usage = [_field_use(nodes[m.id], fields, c.language) for m in ms]
            P = Q = 0
            for a in range(len(usage)):
                for b in range(a + 1, len(usage)):
                    if usage[a] & usage[b]:
                        Q += 1
                    else:
                        P += 1
            # CBO: other project classes referenced anywhere inside the class body
            refs: set[str] = set()
            stack = [nodes[c.id]]
            while stack:
                n = stack.pop()
                if n.child_count == 0 and n.type in ("identifier", "type_identifier"):
                    t = ts.text(n)
                    if t in names and t != c.name:
                        refs.add(t)
                else:
                    stack.extend(n.children)
            ctx.add_metrics(c.id, {
                "wmc": wmc, "dit": dit(c.id), "noc": noc[c.id], "cbo": len(refs), "rfc": rfc,
                "lcom": max(P - Q, 0), "external_base_classes": len(external_bases[c.id]),
            })
            c.details["oo_notes"] = {
                "external_bases": external_bases[c.id], "coupled_classes": sorted(refs)[:30],
                "approximation": "CBO/RFC/LCOM are syntactic approximations; no type resolution was performed.",
            }
        return f"CK metrics for {len(classes)} classes/structs"


def _field_use(fn, fields: set, language: str) -> set:
    used: set = set()
    stack = [fn.child_by_field_name("body") or fn]
    while stack:
        n = stack.pop()
        if language == "python":
            if n.type == "attribute":
                obj, attr = n.child_by_field_name("object"), n.child_by_field_name("attribute")
                if obj is not None and attr is not None and ts.text(obj) in ("self", "cls") \
                        and ts.text(attr) in fields:
                    used.add(ts.text(attr))
        elif n.type in ("identifier", "field_identifier") and n.child_count == 0 and ts.text(n) in fields:
            used.add(ts.text(n))
        stack.extend(n.children)
    return used


# ------------------------------------------------------------------ hotspots
class StructuralHotspotPass(AnalysisPass):
    name = "structural_hotspots"
    description = "Flag structural complexity indicators. These are NOT defect predictions."
    requires = ("entities", "basic_metrics", "complexity_metrics")
    produces = ("hotspots",)
    languages = LANGS
    granularity = ("function", "class")

    def run(self, ctx: PassContext) -> str:
        t = ctx.config.thresholds
        entities: list[Entity] = ctx.get("entities")
        out: list[Hotspot] = []

        def add(e: Entity, rule: str, sev: str, value: float, thr: float, msg: str) -> None:
            out.append(Hotspot(
                id=f"{e.id}#{rule}", layer="structural", entity_id=e.id, granularity=e.kind,  # type: ignore[arg-type]
                path=e.path, range=e.range, rule=rule, severity=sev, value=value, threshold=thr, message=msg,  # type: ignore[arg-type]
            ))

        for e in entities:
            m = ctx.metrics.get(e.id, {})
            if e.kind == "function":
                cc = m.get("cyclomatic", 0)
                if cc >= t.cyclomatic_warning:
                    sev = "high" if cc >= t.cyclomatic_high else "warning"
                    top = sorted(e.details.get("complexity_contributors", {}).items(), key=lambda kv: -kv[1])[:3]
                    why = ", ".join(f"{v}× {k}" for k, v in top)
                    add(e, "high_cyclomatic_complexity", sev, cc,
                        t.cyclomatic_high if sev == "high" else t.cyclomatic_warning,
                        f"Cyclomatic complexity {int(cc)}. Main contributors: {why}.")
                nd = m.get("nesting_depth", 0)
                if nd >= t.nesting_warning:
                    sev = "high" if nd >= t.nesting_high else "warning"
                    add(e, "deep_nesting", sev, nd, t.nesting_high if sev == "high" else t.nesting_warning,
                        f"Control structures nested {int(nd)} levels deep (deepest near line "
                        f"{e.details.get('max_nesting_line')}).")
                sl = m.get("sloc", 0)
                if sl >= t.function_sloc_warning:
                    sev = "high" if sl >= t.function_sloc_high else "warning"
                    add(e, "long_function", sev, sl, t.function_sloc_high if sev == "high" else t.function_sloc_warning,
                        f"{int(sl)} source lines of code in one function.")
                pr = m.get("parameters", 0)
                if pr >= t.params_warning:
                    sev = "high" if pr >= t.params_high else "warning"
                    add(e, "long_parameter_list", sev, pr, t.params_high if sev == "high" else t.params_warning,
                        f"{int(pr)} parameters.")
                cases = e.details.get("complexity_contributors", {}).get("case", 0)
                if cases >= 15:
                    add(e, "large_switch", "warning", cases, 15, f"Switch/match with {cases} cases.")
                if m.get("exception_handlers", 0) >= 4:
                    add(e, "complex_error_handling", "info", m["exception_handlers"], 4,
                        f"{int(m['exception_handlers'])} exception handlers in one function.")
                if m.get("alloc_calls", 0) > m.get("free_calls", 0) and m.get("alloc_calls", 0) > 0:
                    add(e, "resource_ownership_indicator", "info", m["alloc_calls"] - m["free_calls"], 0,
                        "Acquires more resources than it releases locally. May be intentional ownership "
                        "transfer; this is an indicator for review, not a confirmed leak.")
            elif e.kind == "class":
                if m.get("method_count", 0) >= t.class_methods_warning or m.get("sloc", 0) >= t.class_sloc_warning:
                    add(e, "god_class_tendency", "warning", m.get("method_count", 0), t.class_methods_warning,
                        f"{int(m.get('method_count', 0))} methods and {int(m.get('sloc', 0))} SLOC: a large class "
                        f"may be taking on several responsibilities.")
        ctx.put("hotspots", out)
        return f"{len(out)} structural indicators"


# ------------------------------------------------------------------ project summary
def _hist(values: list[float], edges: list[float]) -> list[dict]:
    bins = [0] * (len(edges))
    for v in values:
        for i in range(len(edges) - 1, -1, -1):
            if v >= edges[i]:
                bins[i] += 1
                break
    out = []
    for i, e in enumerate(edges):
        hi = edges[i + 1] - 1 if i + 1 < len(edges) else None
        out.append({"label": f"{int(e)}+" if hi is None else (f"{int(e)}" if hi == e else f"{int(e)}-{int(hi)}"),
                    "count": bins[i], "min": e})
    return out


class ProjectSummaryPass(AnalysisPass):
    name = "project_summary"
    description = "Aggregate project, directory and language level statistics and distributions."
    requires = ("entities", "basic_metrics", "complexity_metrics", "hotspots", "files")
    produces = ("summary",)
    languages = LANGS
    granularity = ("project", "directory")

    def run(self, ctx: PassContext) -> str:
        entities: list[Entity] = ctx.get("entities")
        hotspots: list[Hotspot] = ctx.get("hotspots")
        M = ctx.metrics
        files = [e for e in entities if e.kind == "file"]
        funcs = [e for e in entities if e.kind == "function"]
        classes = [e for e in entities if e.kind == "class"]

        def tot(items, k): return sum(M.get(i.id, {}).get(k, 0) for i in items)

        cc = [M[f.id]["cyclomatic"] for f in funcs]
        by_lang: dict = {}
        for lang in sorted({e.language for e in entities}):
            fl = [f for f in files if f.language == lang]
            fn = [f for f in funcs if f.language == lang]
            by_lang[lang] = {
                "files": len(fl), "sloc": tot(fl, "sloc"), "functions": len(fn),
                "classes": sum(1 for c in classes if c.language == lang),
                "mean_cyclomatic": round(sum(M[f.id]["cyclomatic"] for f in fn) / len(fn), 2) if fn else 0,
                "max_cyclomatic": max((M[f.id]["cyclomatic"] for f in fn), default=0),
            }
        dirs: dict[str, dict] = defaultdict(lambda: {"files": 0, "sloc": 0, "functions": 0, "max_cyclomatic": 0, "hotspots": 0})
        hot_by_path = Counter(h.path for h in hotspots)
        for f in files:
            d = f.path.rsplit("/", 1)[0] if "/" in f.path else "."
            parts = d.split("/") if d != "." else ["."]
            for k in range(1, len(parts) + 1):  # contribute to every ancestor directory
                key = "/".join(parts[:k])
                r = dirs[key]
                r["files"] += 1
                r["sloc"] += M[f.id]["sloc"]
                r["functions"] += M[f.id].get("function_count", 0)
                r["max_cyclomatic"] = max(r["max_cyclomatic"], M[f.id].get("max_cyclomatic", 0))
                r["hotspots"] += hot_by_path[f.path]

        def brief(e: Entity) -> dict:
            return {"id": e.id, "name": e.qualified_name, "path": e.path, "start_line": e.range.start_line,
                    "cyclomatic": M[e.id]["cyclomatic"], "sloc": M[e.id]["sloc"],
                    "nesting_depth": M[e.id]["nesting_depth"], "parameters": M[e.id]["parameters"]}

        sev = Counter(h.severity for h in hotspots)
        rules = Counter(h.rule for h in hotspots)
        summary = {
            "totals": {
                "files": len(files), "sloc": tot(files, "sloc"), "loc": tot(files, "loc"),
                "comment_lines": tot(files, "comment_lines"), "blank_lines": tot(files, "blank_lines"),
                "functions": len(funcs), "classes": len(classes),
                "methods": sum(1 for f in funcs if f.details.get("is_method")),
                "mean_cyclomatic": round(sum(cc) / len(cc), 2) if cc else 0,
                "max_cyclomatic": max(cc) if cc else 0,
                "comment_ratio": round(tot(files, "comment_lines") / max(1, tot(files, "sloc")), 3),
            },
            "by_language": by_lang,
            "by_directory": dict(dirs),
            "distributions": {
                "cyclomatic": _hist(cc, [1, 2, 4, 6, 11, 21, 51]),
                "function_sloc": _hist([M[f.id]["sloc"] for f in funcs], [0, 5, 10, 20, 40, 80, 160]),
                "nesting_depth": _hist([M[f.id]["nesting_depth"] for f in funcs], [0, 1, 2, 3, 4, 5, 6]),
            },
            "hotspot_counts": {"by_severity": dict(sev), "by_rule": dict(rules), "layer": "structural"},
            "top_complex_functions": [brief(e) for e in sorted(funcs, key=lambda e: -M[e.id]["cyclomatic"])[:20]],
            "top_files": [
                {"path": f.path, "sloc": M[f.id]["sloc"], "max_cyclomatic": M[f.id].get("max_cyclomatic", 0),
                 "functions": M[f.id].get("function_count", 0), "hotspots": hot_by_path[f.path]}
                for f in sorted(files, key=lambda f: -(M[f.id].get("max_cyclomatic", 0)))[:20]
            ],
        }
        ctx.put("summary", summary)
        return "Project summary computed"
