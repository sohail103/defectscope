"""Foundation passes: discovery -> parsing -> symbol index."""
from __future__ import annotations

from ...core import config
from ...core.schemas import Entity, FileInfo, SourceRange
from ...parsers import treesitter as ts
from ...projects.discovery import discover
from ..base import AnalysisPass, PassContext

LANGS = frozenset({"python", "c", "cpp"})


class DiscoveryPass(AnalysisPass):
    name = "project_discovery"
    description = "Walk the project, apply exclusion rules, detect languages, roles and build systems."
    produces = ("files", "discovery_summary")
    granularity = ("project",)

    def run(self, ctx: PassContext) -> str:
        files, summary = discover(ctx.root, ctx.config.exclusions)
        analysable = [f for f in files if f.language and not f.excluded]
        if len(analysable) > config.MAX_ANALYSED_FILES:
            ctx.warn(f"{len(analysable)} analysable files; truncated to {config.MAX_ANALYSED_FILES}")
            analysable = analysable[: config.MAX_ANALYSED_FILES]
        ctx.put("files", analysable)
        ctx.put("all_files", files)
        ctx.put("discovery_summary", summary)
        return f"{len(analysable)} analysable files ({summary['excluded_files']} excluded)"


class ParsingPass(AnalysisPass):
    name = "source_parsing"
    description = "Parse each file with Tree-sitter (syntax-level only; no macro expansion or type resolution)."
    requires = ("files",)
    produces = ("parsed_files", "parse_status")
    languages = LANGS
    granularity = ("file",)

    def run(self, ctx: PassContext) -> str:
        files: list[FileInfo] = ctx.get("files")
        parsers: dict[str, object] = {}
        parsed, status = {}, {}
        for i, f in enumerate(files):
            ctx.progress(i / max(1, len(files)), f.path)
            try:
                src = (ctx.root / f.path).read_bytes()
                parser = parsers.setdefault(f.language, ts.new_parser(f.language))
                pf = ts.parse_source(f.path, f.language, src, parser)  # type: ignore[arg-type]
            except Exception as e:  # noqa: BLE001
                ctx.warn(f"{f.path}: parse failed ({e})")
                status[f.path] = {"ok": False, "syntax_errors": -1, "level": "unparsed"}
                continue
            parsed[f.path] = pf
            status[f.path] = {
                "ok": not pf.has_syntax_errors, "syntax_errors": pf.error_nodes,
                # Honest labelling: a clean parse is syntax-level knowledge only.
                "level": "syntax",
            }
            if pf.has_syntax_errors:
                ctx.warn(f"{f.path}: {pf.error_nodes} syntax error node(s); metrics may be incomplete")
        ctx.put("parsed_files", parsed)
        ctx.put("parse_status", status)
        bad = sum(1 for s in status.values() if not s["ok"])
        return f"Parsed {len(parsed)} files; {bad} with syntax problems. Level: syntax only."


def _range(node) -> SourceRange:
    (sr, sc), (er, ec) = node.start_point, node.end_point
    end_line = er + 1 if (ec > 0 or er == sr) else er  # node ending at col 0 is exclusive
    return SourceRange(start_line=sr + 1, end_line=max(end_line, sr + 1), start_col=sc, end_col=ec)


def _python_fields(class_node) -> list[str]:
    """Class attributes plus `self.x = ...` assignments in methods."""
    fields: list[str] = []
    body = class_node.child_by_field_name("body")
    if body is None:
        return fields
    stack = list(body.named_children)
    while stack:
        n = stack.pop()
        t = n.type
        if t == "decorated_definition":
            stack.extend(n.named_children)
        elif t == "expression_statement":
            a = n.named_children[0] if n.named_children else None
            if a is not None and a.type in ("assignment", "augmented_assignment"):
                left = a.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    fields.append(ts.text(left))
        elif t == "function_definition":
            inner = [n.child_by_field_name("body")]
            while inner:
                m = inner.pop()
                if m is None:
                    continue
                if m.type in ("function_definition", "class_definition"):
                    continue
                if m.type in ("assignment", "augmented_assignment"):
                    left = m.child_by_field_name("left")
                    if left is not None and left.type == "attribute":
                        obj = left.child_by_field_name("object")
                        attr = left.child_by_field_name("attribute")
                        if obj is not None and attr is not None and ts.text(obj) in ("self", "cls"):
                            fields.append(ts.text(attr))
                inner.extend(m.children)
    seen: dict[str, None] = {}
    for f in fields:
        seen.setdefault(f, None)
    return list(seen)


def _c_fields(class_node) -> tuple[list[str], list[str]]:
    body = class_node.child_by_field_name("body")
    fields, methods = [], []
    if body is None:
        return fields, methods
    for c in body.named_children:
        if c.type == "field_declaration":
            for d in c.children_by_field_name("declarator"):
                name = ts.c_declarator_name(d)
                (methods if _has_function_declarator(d) else fields).append(name)
        elif c.type == "declaration":  # method declarations in some grammars
            for d in c.children_by_field_name("declarator"):
                methods.append(ts.c_declarator_name(d))
    return fields, methods


def _has_function_declarator(d) -> bool:
    while d is not None:
        if d.type == "function_declarator":
            return True
        d = d.child_by_field_name("declarator")
    return False


class SymbolIndexPass(AnalysisPass):
    name = "symbol_index"
    description = "Extract files, classes/structs and functions/methods with source ranges and parent scopes."
    requires = ("parsed_files",)
    produces = ("entities", "entity_nodes")
    languages = LANGS
    granularity = ("file", "class", "function")

    def run(self, ctx: PassContext) -> str:
        parsed: dict[str, ts.ParsedFile] = ctx.get("parsed_files")
        entities: list[Entity] = []
        nodes: dict[str, object] = {}
        for i, (path, pf) in enumerate(parsed.items()):
            ctx.progress(i / max(1, len(parsed)), path)
            entities.extend(self._extract(pf, nodes))
        self._link_methods(entities)
        ctx.put("entities", entities)
        ctx.put("entity_nodes", nodes)
        c = sum(e.kind == "class" for e in entities)
        f = sum(e.kind == "function" for e in entities)
        return f"{len(parsed)} files, {c} classes/structs, {f} functions/methods"

    def _extract(self, pf: ts.ParsedFile, nodes: dict) -> list[Entity]:
        spec = ts.SPECS[pf.language]
        sep = "." if pf.language == "python" else "::"
        root = pf.tree.root_node
        out: list[Entity] = []
        file_ent = Entity(
            id=pf.path, kind="file", name=pf.path.rsplit("/", 1)[-1], qualified_name=pf.path,
            language=pf.language, path=pf.path, range=SourceRange(start_line=1, end_line=max(1, pf.source.count(b"\n") + (0 if pf.source.endswith(b"\n") or not pf.source else 1))),
            details={"syntax_errors": pf.error_nodes},
        )
        out.append(file_ent)
        nodes[file_ent.id] = root
        # stack items: (node, scope names, parent entity id, enclosing class qualified name)
        stack = [(root, (), file_ent.id, None)]
        while stack:
            node, scope, parent_id, cls = stack.pop()
            t = node.type
            if t in spec.function_types:
                raw = ts.function_name(node, pf.language)
                scope_extra, _, name = raw.rpartition("::")
                full_scope = scope + tuple(s for s in scope_extra.split("::") if s)
                qname = sep.join(full_scope + (name,))
                ent = Entity(
                    id=f"{pf.path}::{qname}@{node.start_point[0] + 1}", kind="function", name=name,
                    qualified_name=qname, language=pf.language, path=pf.path, range=_range(node),
                    parent_id=parent_id, parent_scope=sep.join(full_scope) or None,
                    details={"is_method": cls is not None or bool(scope_extra), "class": cls or scope_extra or None},
                )
                out.append(ent)
                nodes[ent.id] = node
                new_scope = scope + (name,)
                for ch in reversed(node.named_children):
                    stack.append((ch, new_scope, ent.id, None))
                continue
            if t in spec.class_types and ts.class_has_body(node, pf.language):
                name = ts.class_name(node, pf.language) or f"<anonymous {t.split('_')[0]}>"
                qname = sep.join(scope + (name,))
                ent = Entity(
                    id=f"{pf.path}::{qname}@{node.start_point[0] + 1}", kind="class", name=name,
                    qualified_name=qname, language=pf.language, path=pf.path, range=_range(node),
                    parent_id=parent_id, parent_scope=sep.join(scope) or None,
                    details={"construct": t.split("_")[0], "bases": ts.base_classes(node, pf.language)},
                )
                if pf.language == "python":
                    ent.details["fields"] = _python_fields(node)
                else:
                    fields, methods = _c_fields(node)
                    ent.details["fields"], ent.details["declared_methods"] = fields, methods
                out.append(ent)
                nodes[ent.id] = node
                for ch in reversed(node.named_children):
                    stack.append((ch, scope + (name,), ent.id, qname))
                continue
            if t == "namespace_definition":
                n = node.child_by_field_name("name")
                nscope = scope + ((ts.text(n),) if n is not None else ())
                for ch in reversed(node.named_children):
                    stack.append((ch, nscope, parent_id, cls))
                continue
            for ch in reversed(node.named_children):
                stack.append((ch, scope, parent_id, cls))
        return out

    @staticmethod
    def _link_methods(entities: list[Entity]) -> None:
        """Record each method's class entity, including out-of-class C++ definitions (Foo::bar)."""
        by_name: dict[str, list[Entity]] = {}
        for e in entities:
            if e.kind == "class":
                by_name.setdefault(e.qualified_name, []).append(e)
                by_name.setdefault(e.name, []).append(e)
        idx = {e.id: e for e in entities}

        def stem(p: str) -> str:
            return p.rsplit(".", 1)[0]

        for e in entities:
            if e.kind != "function":
                continue
            parent = idx.get(e.parent_id or "")
            if parent is not None and parent.kind == "class":
                e.details["class_entity_id"] = parent.id
            elif e.language == "cpp" and e.details.get("class"):
                cands = by_name.get(e.details["class"], [])
                same = [c for c in cands if stem(c.path) == stem(e.path)]
                pick = (same or cands)[:1]
                if pick:
                    e.details["class_entity_id"] = pick[0].id
