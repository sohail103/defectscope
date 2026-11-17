# Limitations

## Not implemented (specified but not built)
* Experiment A (static vs historical): history features exist but there is no history-labelled dataset to train or evaluate with.
* Function-level history (changes are attributed to files only). Historical features are not used by any model.
* Codeflaws, BugsInPy adapters and experiments; LINE-DP / line-level localisation.
* Version comparison mode; HTML/PDF reports (CSV and JSON export exist).
* Statement/expression/line granularity (entities stop at function/class). Clone detection is function-level and structural only.
* Monaco editor, React Flow, WebSockets (custom viewer, hand-written SVG, polling are used instead). SQLite (JSON files are used).
* No component or end-to-end frontend tests. Backend: 22 tests (sample-project metrics, secure extraction, API flow, ML metrics/leakage/calibration/compatibility/explanations, tool findings, tool-config isolation, history and cutoff, clones, priorities).

## Analysis limits
* Syntax-level only. No macro expansion, include/type resolution, data flow or semantic claims. Calls are matched by name. CBO/RFC/LCOM are syntactic approximations.
* Python dynamic features (decorators, `getattr`, runtime imports) are invisible. Tree-sitter error recovery can yield partial metrics for files with syntax errors; these are flagged.
* Cognitive complexity and Halstead counts follow simplified rules (see METRICS.md). Columns are byte offsets.
* Dependency resolution is by path/name matching.
* Large projects: files over the size limit or beyond 5000 analysable files are skipped (reported). Parse trees are held in memory.

## Static-analysis and history limits
* Tool findings are not validated against labelled defects here; false positives and false negatives are expected. Severity is the tool's own.
* cppcheck runs without a build configuration (macros and include paths unresolved). clang-tidy gives semantic results only for files it can compile; without
  `compile_commands.json` (or with one that has another machine's absolute paths) many files will fail to compile and are reported as incomplete.
* Pylint runs without the project's dependencies installed, so import and some type results are suppressed. Large projects can exceed the tool timeouts (partial results are flagged).
* Python tools see only Python files; C/C++ tools see only C/C++ files. Only the first 100 files are analysed by clang-tidy, 1500 per tool otherwise.
* History: merges excluded, renames not followed, shallow clones incomplete, e-mail used as author identity, bug-fix commits are a keyword heuristic, up to 3000 commits read.
  Reading a repository runs the `git` program on untrusted data (with hooks, fsmonitor and global config disabled, but the repository's own config is still read).
* Complexity over time samples a few commits and skips files over the size cap or that fail to parse at old revisions.

## Prediction limits
* The only defect data used is NASA MDP (four projects, one organisation, mostly 1990s-2000s flight/ground software). Transfer to modern open-source code is unvalidated.
* Models see re-measured, approximate features rather than the original tool's values; distribution shift is likely. Out-of-range metrics are flagged, but in-range shift is not detected.
* Probabilities are calibrated to NASA training defect rates, not to your project.
* Predictions are for whole C/C++ functions. No Python model exists. No line-level predictions are made.
* Explanations are model-relative correlations, never causal claims. Correlated features (LOC, Halstead) share credit arbitrarily.
* Results from random-split CV are optimistic even on deduplicated data; cross-project numbers are more realistic but still from four projects.

## Operational
* Jobs run in-process and are lost on restart. Everything is single-user and unauthenticated; it must stay bound to localhost.
* Uploaded code is never executed, but parsers process untrusted input; do not expose the port.
* `joblib` model files are pickles: only load models created by your own installation.
