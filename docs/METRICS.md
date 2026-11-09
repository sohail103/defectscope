# Metric definitions

All metrics come from the Tree-sitter syntax tree. They are **syntax-level**: macros are not expanded, includes and types are not resolved,
and Python dynamic behaviour is invisible. Columns are byte offsets. `.h` headers are parsed as C++ if the project has any C++ sources, else C.

## Lines
* `loc`: physical lines spanned by the entity. `blank_lines`, `comment_lines` (comment-only), `code_and_comment_lines` (code with a trailing comment).
* `sloc`: lines containing code (including those with a trailing comment). Python bare string statements (docstrings) count as comments.
* `executable_lines`: distinct lines on which an executable statement begins (declarations excluded). Approximates NASA `LOC_EXECUTABLE`.

## Cyclomatic complexity (`cyclomatic`)
`1 + decision points` within the function (nested function/class definitions are separate entities). Decision points:
* Python: `if`, `elif`, `for`, `while`, `except`, conditional expression, `match` case, comprehension `for`/`if`, `and`/`or`.
* C/C++: `if` (including `else if`), `for`, range-for, `while`, `do`, `case` with a value (not `default`), `?:`, `catch`, `&&`, `||`.

`complexity_contributors` lists the count per construct; `contributor_lines` records where each occurs (the UI highlights them).

## Other complexity
* `nesting_depth`: deepest nesting of `if/for/while/do/switch/try/match`; an `else if` chain does not add depth.
* `cognitive`: **simplified** Sonar-style: +1 per structure plus nesting depth, +1 per `elif/else if/else`, +1 per run of identical logical operators. Approximation.
* `branches`, `loops`, `returns`, `exception_handlers`, `logical_operators`, `distinct_calls` (callee names, matched by name only),
  `pointer_ops`, `alloc_calls`/`free_calls` (malloc/calloc/realloc/strdup/fopen/open/new vs free/fclose/close/delete), `goto_count`, `global_refs`.
* `parameters`: Python excludes a leading `self`/`cls`; C `(void)` counts 0. `local_variables`: Python distinct assigned names; C declarators.

## Halstead (token-level approximation)
Operands = named leaf nodes (identifiers, literals). Operators = anonymous leaf tokens except `; , ) ] } :`. Then
`n = n1+n2`, `N = N1+N2`, `V = N·log2(n)`, `D = (n1/2)·(N2/n2)`, `E = D·V`, `L = 1/D`, `T = E/18`, `B = V/3000`.
The NASA tool tokenises differently, so values are comparable in spirit, not exactly.

## Object-oriented (CK) metrics, classes/structs only
* `wmc`: sum of method cyclomatic complexity. `dit`/`noc`: from base classes resolved *by simple name* within the project (external bases are reported, not counted).
* `cbo` (approx): distinct other project classes whose names appear in the class body. `rfc` (approx): methods + distinct called names.
* `lcom`: CK original `max(P−Q, 0)` over method pairs sharing no fields (P) vs sharing at least one (Q); field use is syntactic.
Ambiguous class names produce a warning. For C, structs get size/field metrics but few OO metrics are meaningful.

## Dependencies
File-level graph from Python imports (module-name matching, relative imports) and C/C++ `#include` (relative path, then path-suffix match).
Reports fan-in, fan-out, instability `fo/(fi+fo)`, cycles (Tarjan SCC) and external dependencies. Dynamic imports and include-path configuration are not resolved.

## Structural hotspots (thresholds are configurable)
High cyclomatic (≥10 warning, ≥20 high), deep nesting (≥4/≥6), long function (≥60/≥120 SLOC), long parameter list (≥5/≥8), large switch (≥15 cases),
many exception handlers (≥4), resource-ownership indicator (more acquisitions than releases locally), god-class tendency (≥20 methods or ≥400 SLOC).
They are heuristics for review, **not** defect findings. Duplicate-code detection is not implemented.
