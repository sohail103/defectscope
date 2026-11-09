# Limitations

## Not implemented (specified but not built)
* Static-analysis integrations (Clang/clang-tidy/cppcheck/Ruff/Pylint/Bandit) and `compile_commands.json` semantic analysis. The UI lane is reserved but empty.
* Git history analysis, historical features and Experiment A (static vs historical). Needs history-labelled data too.
* Codeflaws, BugsInPy adapters and experiments; LINE-DP / line-level localisation.
* Version comparison mode; HTML/PDF reports (CSV and JSON export exist).
* Duplicate-code detection. Statement/expression/line granularity (entities stop at function/class).
* Monaco editor, React Flow, WebSockets (custom viewer, hand-written SVG, polling are used instead). SQLite (JSON files are used).
* No component or end-to-end frontend tests. Backend: 15 tests (known metric values on a sample project, secure extraction, API flow, metrics, leakage, calibration, compatibility, explanation accuracy).

## Analysis limits
* Syntax-level only. No macro expansion, include/type resolution, data flow or semantic claims. Calls are matched by name. CBO/RFC/LCOM are syntactic approximations.
* Python dynamic features (decorators, `getattr`, runtime imports) are invisible. Tree-sitter error recovery can yield partial metrics for files with syntax errors; these are flagged.
* Cognitive complexity and Halstead counts follow simplified rules (see METRICS.md). Columns are byte offsets.
* Dependency resolution is by path/name matching.
* Large projects: files over the size limit or beyond 5000 analysable files are skipped (reported). Parse trees are held in memory.

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
