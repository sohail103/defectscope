"""Tree-sitter parsing and per-language node-type specifications.

Everything downstream (symbols, complexity, metrics) is driven by `LangSpec`, so adding a
language means adding a spec + a name extractor rather than touching the analysis passes.

NOTE: this is *syntax-level* analysis only. Tree-sitter does not expand macros, resolve
includes or types. Semantic claims need Clang (C/C++) or Python's runtime/type info.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_python
from tree_sitter import Language, Node, Parser, Tree


@dataclass(frozen=True)
class LangSpec:
    name: str
    function_types: frozenset
    class_types: frozenset
    # decision node type -> label used in the complexity breakdown
    branch_types: dict
    nesting_types: frozenset
    loop_types: frozenset
    handler_types: frozenset
    import_types: frozenset
    logical_ops: frozenset
    comment_types: frozenset = frozenset({"comment"})


PYTHON = LangSpec(
    name="python",
    function_types=frozenset({"function_definition"}),
    class_types=frozenset({"class_definition"}),
    branch_types={
        "if_statement": "if", "elif_clause": "elif", "for_statement": "for", "while_statement": "while",
        "except_clause": "except", "conditional_expression": "ternary", "case_clause": "case",
        "for_in_clause": "comprehension_for", "if_clause": "comprehension_if",
    },
    nesting_types=frozenset({"if_statement", "for_statement", "while_statement", "try_statement", "match_statement"}),
    loop_types=frozenset({"for_statement", "while_statement"}),
    handler_types=frozenset({"except_clause"}),
    import_types=frozenset({"import_statement", "import_from_statement"}),
    logical_ops=frozenset({"and", "or"}),
)

_C_COMMON = dict(
    function_types=frozenset({"function_definition"}),
    branch_types={
        "if_statement": "if", "for_statement": "for", "while_statement": "while", "do_statement": "do_while",
        "case_statement": "case", "conditional_expression": "ternary",
        "for_range_loop": "for", "catch_clause": "catch",
    },
    nesting_types=frozenset({"if_statement", "for_statement", "while_statement", "do_statement",
                             "switch_statement", "for_range_loop", "try_statement"}),
    loop_types=frozenset({"for_statement", "while_statement", "do_statement", "for_range_loop"}),
    handler_types=frozenset({"catch_clause"}),
    import_types=frozenset({"preproc_include"}),
    logical_ops=frozenset({"&&", "||"}),
)

C = LangSpec(name="c", class_types=frozenset({"struct_specifier", "union_specifier"}), **_C_COMMON)
CPP = LangSpec(name="cpp", class_types=frozenset({"class_specifier", "struct_specifier", "union_specifier"}), **_C_COMMON)

SPECS = {"python": PYTHON, "c": C, "cpp": CPP}
_LANG_PTR = {"python": tree_sitter_python.language, "c": tree_sitter_c.language, "cpp": tree_sitter_cpp.language}


@lru_cache(maxsize=None)
def _language(name: str) -> Language:
    return Language(_LANG_PTR[name]())


def new_parser(language: str) -> Parser:
    return Parser(_language(language))


@dataclass
class ParsedFile:
    path: str
    language: str
    source: bytes
    tree: Tree
    error_nodes: int = 0
    lines: list = field(default_factory=list)

    @property
    def has_syntax_errors(self) -> bool:
        return self.error_nodes > 0


def parse_source(path: str, language: str, source: bytes, parser: Optional[Parser] = None) -> ParsedFile:
    parser = parser or new_parser(language)
    tree = parser.parse(source)
    errors = 0
    if tree.root_node.has_error:
        stack = [tree.root_node]
        while stack and errors < 1000:
            n = stack.pop()
            if n.type == "ERROR" or n.is_missing:
                errors += 1
            if n.has_error:
                stack.extend(n.children)
    return ParsedFile(path=path, language=language, source=source, tree=tree, error_nodes=errors)


def text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


# ---------------------------------------------------------------- name extraction

_DECL_WRAPPERS = {"function_declarator", "pointer_declarator", "reference_declarator",
                  "array_declarator", "attributed_declarator", "parenthesized_declarator"}


def c_declarator_name(decl: Optional[Node]) -> str:
    """Descend a C/C++ declarator chain to the declared identifier."""
    while decl is not None and decl.type in _DECL_WRAPPERS:
        nxt = decl.child_by_field_name("declarator")
        if nxt is None:
            nxt = next((c for c in decl.children if c.is_named), None)
        decl = nxt
    return text(decl) if decl is not None else "<anonymous>"


def function_name(node: Node, language: str) -> str:
    if language == "python":
        n = node.child_by_field_name("name")
        return text(n) if n is not None else "<anonymous>"
    return c_declarator_name(node.child_by_field_name("declarator"))


def class_name(node: Node, language: str) -> Optional[str]:
    n = node.child_by_field_name("name")
    return text(n) if n is not None else None


def class_has_body(node: Node, language: str) -> bool:
    if language == "python":
        return True
    return node.child_by_field_name("body") is not None


def base_classes(node: Node, language: str) -> list[str]:
    out: list[str] = []
    if language == "python":
        args = node.child_by_field_name("superclasses")
        if args is not None:
            out = [text(c) for c in args.named_children if c.type in ("identifier", "attribute")]
    elif language == "cpp":
        for c in node.children:
            if c.type == "base_class_clause":
                out = [text(x) for x in c.named_children if x.type in ("type_identifier", "qualified_identifier", "template_type")]
    return [b.split(".")[-1].split("::")[-1] for b in out]
