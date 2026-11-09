"""Metric passes. Each pass has one responsibility; values are attached per entity id.

Metric definitions (see docs/METRICS.md):
  loc            physical lines spanned by the entity
  sloc           lines containing code (not blank, not comment-only; Python docstrings count as comments)
  cyclomatic     McCabe: 1 + decision points (if/elif/for/while/case/catch/except/ternary/&&/||/...)
  nesting_depth  maximum depth of nested control structures (else-if chains are not counted as nesting)
  cognitive      simplified Sonar-style cognitive complexity (approximation)
"""
from __future__ import annotations

import math
from collections import Counter

from ...core.schemas import Entity
from ...parsers import treesitter as ts
from ..base import AnalysisPass, PassContext
from .core import LANGS


# ------------------------------------------------------------------ line classification
class LineClasses:
    """Per-line blank/comment/code classification with prefix sums for O(1) range queries."""

    def __init__(self, pf: ts.ParsedFile):
        spec = ts.SPECS[pf.language]
        src = pf.source
        mask = bytearray(len(src))
        stack = [pf.tree.root_node]
        while stack:
            n = stack.pop()
            if n.type in spec.comment_types or (
                pf.language == "python" and n.type == "expression_statement"
                and n.child_count == 1 and n.children[0].type == "string"
            ):
                mask[n.start_byte:n.end_byte] = b"\x01" * (n.end_byte - n.start_byte)
            else:
                stack.extend(n.children)
        kinds: list[int] = []  # 0 blank, 1 comment-only, 2 code-only, 3 code with trailing comment
        off = 0
        raw_lines = src.split(b"\n")
        if raw_lines and raw_lines[-1] == b"":
            raw_lines.pop()
        for seg in raw_lines:
            stripped = seg.strip()
            if not stripped:
                kinds.append(0)
            else:
                lead = len(seg) - len(seg.lstrip())
                trail = len(seg) - len(seg.rstrip())
                inner = mask[off + lead: off + len(seg) - trail]
                has_code, has_comment = inner.find(0) != -1, inner.find(1) != -1
                kinds.append(1 if not has_code else 3 if has_comment else 2)
            off += len(seg) + 1
        self.n = len(kinds)
        self._pre = [[0] for _ in range(4)]
        for k in kinds:
            for j in range(4):
                self._pre[j].append(self._pre[j][-1] + (1 if k == j else 0))

    def count(self, kind: int, start_line: int, end_line: int) -> int:
        a, b = max(0, start_line - 1), min(self.n, end_line)
        return self._pre[kind][b] - self._pre[kind][a] if b > a else 0

    def blank(self, a, b): return self.count(0, a, b)
    def comment(self, a, b): return self.count(1, a, b)  # comment-only lines
    def mixed(self, a, b): return self.count(3, a, b)  # code lines that also carry a comment
    def code(self, a, b): return self.count(2, a, b) + self.count(3, a, b)


def _params(node, language: str) -> int:
    p = node.child_by_field_name("parameters") if language == "python" else None
    if language == "python":
        if p is None:
            return 0
        names = [c for c in p.named_children if c.type != "comment"]
        if names and ts.text(names[0]).split(":")[0].split("=")[0].strip() in ("self", "cls"):
            names = names[1:]
        return len(names)
    d = node.child_by_field_name("declarator")
    while d is not None and d.type != "function_declarator":
        d = d.child_by_field_name("declarator")
    if d is None:
        return 0
    pl = d.child_by_field_name("parameters")
    if pl is None:
        return 0
    params = [c for c in pl.named_children if c.type in (
        "parameter_declaration", "optional_parameter_declaration", "variadic_parameter_declaration",
        "variadic_parameter")]
    if len(params) == 1 and ts.text(params[0]).strip() == "void":
        return 0
    return len(params)


class BasicMetricsPass(AnalysisPass):
    name = "basic_metrics"
    description = "Line counts, function/class counts, parameters, fields, imports."
    requires = ("entities", "entity_nodes", "parsed_files")
    produces = ("basic_metrics",)
    languages = LANGS
    granularity = ("file", "class", "function")

    def run(self, ctx: PassContext) -> str:
        entities: list[Entity] = ctx.get("entities")
        nodes = ctx.get("entity_nodes")
        parsed = ctx.get("parsed_files")
        by_file: dict[str, list[Entity]] = {}
        for e in entities:
            by_file.setdefault(e.path, []).append(e)
        total = len(by_file)
        for i, (path, ents) in enumerate(by_file.items()):
            ctx.progress(i / max(1, total), path)
            pf = parsed[path]
            spec = ts.SPECS[pf.language]
            lc = LineClasses(pf)
            funcs = [e for e in ents if e.kind == "function"]
            classes = [e for e in ents if e.kind == "class"]
            for e in ents:
                r = e.range
                if e.kind == "file":
                    continue
                m = {
                    "loc": r.end_line - r.start_line + 1,
                    "sloc": lc.code(r.start_line, r.end_line),
                    "comment_lines": lc.comment(r.start_line, r.end_line),
                    "blank_lines": lc.blank(r.start_line, r.end_line),
                    "code_and_comment_lines": lc.mixed(r.start_line, r.end_line),
                }
                if e.kind == "function":
                    m["executable_lines"] = executable_lines(nodes[e.id], spec)
                    m["parameters"] = _params(nodes[e.id], e.language)
                    m["local_variables"] = _locals(nodes[e.id], e.language)
                else:
                    m["field_count"] = len(e.details.get("fields", []))
                    methods = {f.name for f in funcs if f.details.get("class_entity_id") == e.id}
                    methods |= set(e.details.get("declared_methods", []))
                    m["method_count"] = len(methods)
                ctx.add_metrics(e.id, m)
            fsloc = [ctx.metrics[f.id]["sloc"] for f in funcs]
            csloc = [ctx.metrics[c.id]["sloc"] for c in classes]
            imports = 0
            stack = [pf.tree.root_node]
            while stack:
                n = stack.pop()
                if n.type in spec.import_types:
                    imports += 1
                else:
                    stack.extend(n.children)
            ctx.add_metrics(path, {
                "loc": lc.n, "sloc": lc.code(1, lc.n), "comment_lines": lc.count(1, 1, lc.n),
                "code_and_comment_lines": lc.mixed(1, lc.n),
                "blank_lines": lc.count(0, 1, lc.n),
                "function_count": len(funcs), "class_count": len(classes),
                "method_count": sum(1 for f in funcs if f.details.get("is_method")),
                "avg_function_sloc": round(sum(fsloc) / len(fsloc), 2) if fsloc else 0.0,
                "max_function_sloc": max(fsloc) if fsloc else 0,
                "avg_class_sloc": round(sum(csloc) / len(csloc), 2) if csloc else 0.0,
                "imports": imports,
            })
        return f"Basic metrics for {total} files"


_EXEC = {
    "c": {"expression_statement", "return_statement", "if_statement", "for_statement", "while_statement",
          "do_statement", "switch_statement", "break_statement", "continue_statement", "goto_statement"},
    "python": {"expression_statement", "return_statement", "if_statement", "for_statement", "while_statement",
               "break_statement", "continue_statement", "pass_statement", "raise_statement", "assert_statement",
               "with_statement"},
}
_EXEC["cpp"] = _EXEC["c"] | {"for_range_loop", "throw_statement"}


def executable_lines(node, spec) -> int:
    """Distinct lines on which an executable statement begins (declarations excluded).
    Approximates the MDP's LOC_EXECUTABLE; the original tool's exact rule is not documented."""
    kinds = _EXEC[spec.name]
    rows: set[int] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in kinds:
            if not (spec.name == "python" and n.type == "expression_statement" and n.child_count == 1
                    and n.children[0].type == "string"):
                rows.add(n.start_point[0])
        stack.extend(n.children)
    return len(rows)


def _locals(node, language: str) -> int:
    names: set[str] = set()
    n_decl = 0
    stack = list(node.named_children)
    while stack:
        n = stack.pop()
        t = n.type
        if language == "python":
            if t in ("function_definition", "class_definition"):
                continue
            if t in ("assignment", "augmented_assignment", "for_statement", "for_in_clause"):
                left = n.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    names.add(ts.text(left))
                elif left is not None and left.type in ("pattern_list", "tuple_pattern"):
                    names.update(ts.text(c) for c in left.named_children if c.type == "identifier")
        else:
            if t == "declaration":
                n_decl += len(n.children_by_field_name("declarator"))
        stack.extend(n.named_children)
    return len(names) if language == "python" else n_decl


# ------------------------------------------------------------------ complexity
ALLOC = {"malloc", "calloc", "realloc", "strdup", "fopen", "open", "new"}
FREE = {"free", "fclose", "close", "delete"}


class ComplexityPass(AnalysisPass):
    name = "complexity_analysis"
    description = "Cyclomatic and cognitive complexity, nesting, branch/loop/return counts, and their contributors."
    requires = ("entities", "entity_nodes")
    produces = ("complexity_metrics", "call_names")
    languages = LANGS
    granularity = ("function",)

    def run(self, ctx: PassContext) -> str:
        entities: list[Entity] = ctx.get("entities")
        nodes = ctx.get("entity_nodes")
        funcs = [e for e in entities if e.kind == "function"]
        calls_by_entity: dict[str, set[str]] = {}
        for i, e in enumerate(funcs):
            if i % 50 == 0:
                ctx.progress(i / max(1, len(funcs)), e.path)
            metrics, detail, calls = analyse_function(nodes[e.id], ts.SPECS[e.language])
            ctx.add_metrics(e.id, metrics)
            e.details.update(detail)
            calls_by_entity[e.id] = calls
        ctx.put("call_names", calls_by_entity)
        ctx.put("complexity_metrics", True)
        # roll up to files
        by_file: dict[str, list[float]] = {}
        for e in funcs:
            by_file.setdefault(e.path, []).append(ctx.metrics[e.id]["cyclomatic"])
        for e in entities:
            if e.kind == "file":
                vals = by_file.get(e.path, [])
                ctx.add_metrics(e.id, {
                    "max_cyclomatic": max(vals) if vals else 0,
                    "total_cyclomatic": sum(vals),
                    "mean_cyclomatic": round(sum(vals) / len(vals), 2) if vals else 0.0,
                })
        return f"Complexity for {len(funcs)} functions"


def analyse_function(fn, spec: ts.LangSpec) -> tuple[dict, dict, set]:
    lang = spec.name
    counts: Counter = Counter()
    contributors: list[dict] = []
    cc, cog, max_nest = 1, 0, 0
    max_nest_line = fn.start_point[0] + 1
    loops = returns = handlers = logical = 0
    pointer_ops = alloc = free = gotos = globals_ = 0
    calls: set[str] = set()
    stack = [(c, 0) for c in reversed(fn.named_children)]

    def add(kind: str, node, depth: int, inc_cc: int = 1) -> None:
        counts[kind] += inc_cc
        if len(contributors) < 150:
            contributors.append({"line": node.start_point[0] + 1, "kind": kind, "depth": depth})

    while stack:
        node, depth = stack.pop()
        t = node.type
        if t in spec.function_types or (t in spec.class_types and lang != "python") \
                or (t == "class_definition"):
            continue  # nested definitions are separate entities

        is_nest = t in spec.nesting_types
        is_elseif = t == "if_statement" and node.parent is not None and node.parent.type == "else_clause"
        child_depth = depth
        if t in spec.branch_types:
            label = spec.branch_types[t]
            if label in ("comprehension_for", "comprehension_if"):
                cc += 1
                add(label, node, depth)
            elif t == "case_statement":
                if node.child_by_field_name("value") is not None:  # `default:` is not a decision
                    cc += 1
                    add("case", node, depth)
            else:
                cc += 1
                add("else-if" if is_elseif else label, node, depth)
                if t == "elif_clause" or is_elseif:
                    cog += 1
                elif t in ("except_clause", "catch_clause"):
                    cog += 1 + max(0, depth - 1)
                    handlers += 1
                elif t == "case_clause":
                    pass
                else:
                    cog += 1 + depth
        elif t in ("switch_statement", "match_statement"):
            cog += 1 + depth
        elif t == "else_clause":
            # `else if` is charged once, on the nested if; only a plain else / loop-else adds here.
            if not any(c.type == "if_statement" for c in node.named_children):
                cog += 1

        if t in spec.loop_types:
            loops += 1
        if is_nest:
            level = depth if is_elseif else depth + 1
            if level > max_nest:
                max_nest, max_nest_line = level, node.start_point[0] + 1
            child_depth = depth if is_elseif else depth + 1

        # logical operators
        if t == "boolean_operator" or (t == "binary_expression" and lang != "python"):
            op = node.child_by_field_name("operator")
            optxt = ts.text(op) if op is not None else ""
            if optxt in spec.logical_ops:
                cc += 1
                logical += 1
                add(optxt, node, depth)
                parent = node.parent
                same_run = parent is not None and parent.type == t and \
                    ts.text(parent.child_by_field_name("operator") or node) == optxt
                if not same_run:
                    cog += 1
        elif t in ("return_statement",):
            returns += 1
        elif t == "goto_statement":
            gotos += 1
        elif t in ("global_statement", "nonlocal_statement"):
            globals_ += 1
        elif t in ("pointer_expression",) or (t == "field_expression" and b"->" in (node.text or b"")[:200]):
            pointer_ops += 1
        elif t == "new_expression":
            alloc += 1
        elif t == "delete_expression":
            free += 1
        elif t in ("call", "call_expression"):
            f = node.child_by_field_name("function")
            if f is not None:
                name = ts.text(f)
                short = name.split(".")[-1].split("->")[-1].split("::")[-1]
                calls.add(short)
                if short in ALLOC:
                    alloc += 1
                elif short in FREE:
                    free += 1

        for ch in reversed(node.named_children):
            stack.append((ch, child_depth))

    contributor_counts = dict(counts)
    metrics = {
        "cyclomatic": cc, "cognitive": cog, "nesting_depth": max_nest,
        "decision_points": cc - 1, "branches": sum(v for k, v in counts.items() if k in (
            "if", "elif", "else-if", "case", "ternary", "except", "catch")),
        "loops": loops, "returns": returns, "exception_handlers": handlers,
        "logical_operators": logical, "distinct_calls": len(calls),
        "pointer_ops": pointer_ops, "alloc_calls": alloc, "free_calls": free,
        "goto_count": gotos, "global_refs": globals_,
    }
    detail = {
        "complexity_contributors": contributor_counts,
        "contributor_lines": contributors,
        "max_nesting_line": max_nest_line,
    }
    return metrics, detail, calls


# ------------------------------------------------------------------ Halstead
_SKIP_OPS = {";", ",", ")", "]", "}", ":"}


class HalsteadPass(AnalysisPass):
    name = "halstead_metrics"
    description = "Token-based Halstead metrics. Operator/operand rules are an approximation (see METRICS.md)."
    requires = ("entities", "entity_nodes")
    produces = ("halstead_metrics",)
    languages = LANGS
    granularity = ("function",)

    def run(self, ctx: PassContext) -> str:
        entities: list[Entity] = ctx.get("entities")
        nodes = ctx.get("entity_nodes")
        funcs = [e for e in entities if e.kind == "function"]
        for i, e in enumerate(funcs):
            if i % 50 == 0:
                ctx.progress(i / max(1, len(funcs)), e.path)
            ctx.add_metrics(e.id, halstead(nodes[e.id], ts.SPECS[e.language]))
        ctx.put("halstead_metrics", True)
        return f"Halstead for {len(funcs)} functions (token-level approximation)"


def halstead(fn, spec) -> dict:
    ops: Counter = Counter()
    operands: Counter = Counter()
    stack = [fn]
    while stack:
        n = stack.pop()
        if n.type in spec.comment_types:
            continue
        if n.child_count == 0:
            tok = ts.text(n)
            if n.is_named:
                operands[tok] += 1
            elif tok and tok not in _SKIP_OPS:
                ops[tok] += 1
        else:
            stack.extend(n.children)
    n1, n2 = len(ops), len(operands)
    N1, N2 = sum(ops.values()), sum(operands.values())
    vocab, length = n1 + n2, N1 + N2
    volume = length * math.log2(vocab) if vocab > 1 else 0.0
    difficulty = (n1 / 2.0) * (N2 / n2) if n2 else 0.0
    effort = difficulty * volume
    return {
        "halstead_n1": n1, "halstead_n2": n2, "halstead_N1": N1, "halstead_N2": N2,
        "halstead_vocabulary": vocab, "halstead_length": length,
        "halstead_volume": round(volume, 3), "halstead_difficulty": round(difficulty, 3),
        "halstead_effort": round(effort, 3),
        "halstead_level": round(1 / difficulty, 5) if difficulty else 0.0,
        "halstead_time": round(effort / 18, 3), "halstead_bugs": round(volume / 3000, 5),
    }
