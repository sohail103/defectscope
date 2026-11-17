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

## Static-analysis findings
Fields: `tool`, `rule`, `severity` (high / warning / info, from the tool's own level), `category`, `path`, range, `message`, `cwe` (when the tool gives one),
`entity_id` (innermost function/class containing the start line), `corroborated_by` (other tools reporting the same category on the same line).
Categories: memory_safety, null_pointer, buffer_bounds, resource_management, uninitialized, control_flow, exception_handling, type_problems,
suspicious_condition, security, maintainability. They come from CWE ids and rule-id prefixes only. Per-entity counts: `diagnostics_total`, `diagnostics_high`.
Rules: Ruff selects `E4,E7,E9,F,B,S,PLE,PLW` (minus S101); Pylint runs errors and warnings with import resolution disabled; Bandit skips B101;
cppcheck enables warning, style, performance, portability; clang-tidy runs `clang-analyzer-*` (core, unix, cplusplus, security, deadcode), `bugprone-*`, selected `cert-*`.

## Git history metrics (file level)
`git_commits`, `git_authors`, `git_added`, `git_deleted`, `git_churn` (added + deleted), `git_fix_commits` (message matches a keyword such as fix/bug/crash/leak: heuristic),
`git_change_entropy` (mean over the file's commits of the Shannon entropy of the commit's churn across files), `git_days_since_last_change` and `git_age_days`
(relative to the reference date: the cutoff, or the newest commit), `git_top_author_share`, `git_recent_commits_90d`. Merges are excluded; renames are not followed.
Complexity over time: cyclomatic statistics at up to 8 evenly spaced commits, using the same rules as the current analysis (max 400 files per snapshot).

## Duplicated structure
Functions with at least `min_function_sloc` (8) lines and `min_nodes` (30) syntax nodes are hashed by their sequence of named node types. Equal hashes form a group.
Identifiers and literals are ignored, so renamed copies match. It does not find reordered or partially edited copies, and similar-by-design functions can match.

## Review priority
Per function: cyclomatic complexity, nesting, SLOC, high-severity findings, file commits and fix-like commits, predicted risk (if a model was applied), clone group size.
A flag is set when the function is in the project's top 10% for complexity/risk, has a high-severity finding, shares structure with another function, or belongs to a file in the top 10%
for churn or fix-like commits. Rows sort by function-level flags first, then file-level flags. There is no combined score.
