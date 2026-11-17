# Architecture

```
frontend (React + TS + Vite) ──HTTP/JSON──> backend (FastAPI)
                                              ├─ projects/     import, secure extraction, discovery, storage
                                              ├─ parsers/      Tree-sitter + per-language specs (LangSpec)
                                              ├─ analysis/     pass framework, manager, runner, passes/, diagnostics/ (tool providers), history/ (Git), priorities.py
                                              ├─ features/     NASA-MDP feature schema + extraction from analysis
                                              ├─ datasets/     adapters (NASAMDPAdapter) with provenance
                                              ├─ preprocessing/ leakage-safe sklearn pipelines
                                              ├─ models/       fitting (calibration, threshold), store (manifests), predict
                                              ├─ evaluation/   metrics + experiments B-F
                                              ├─ explainability/ permutation importance, SHAP, linear decomposition
                                              ├─ jobs.py       background jobs, progress, cancellation
                                              └─ api/          REST routers (projects, lab)
```
The analytical backend has no dependency on the UI; every result is available through the API.

## Analysis passes
Each `AnalysisPass` declares `name`, `requires`, `produces` (artifact names), `languages`, `granularity`. `PassManager` resolves dependencies
topologically, skips passes whose inputs are missing (e.g. after a failure), isolates failures, reports per-pass status/timing/warnings,
and supports cancellation between passes and inside long loops (`ctx.progress`).

```
project_discovery → source_parsing → symbol_index ─┬→ basic_metrics ──┐
                                                   ├→ complexity_analysis ─┬→ structural_hotspots → project_summary
                                                   ├→ halstead_metrics ────┴→ feature_extraction
                                                   ├→ duplicate_code ──→ (feeds structural_hotspots)
                                                   ├→ dependency_analysis
                                                   ├→ oo_metrics (needs complexity + basic)
                                                   ├→ static_analysis (providers: ruff, bandit, pylint, cppcheck, clang-tidy)
                                                   └→ git_history → complexity_history   (optional)
```
Passes write per-entity values with `ctx.add_metrics(entity_id, {...})`; entities carry path, kind, name, qualified name,
start/end line and column, and parent scope. Tree nodes are kept in memory during a run (`entity_nodes`) and never serialised.

Adding a language: add a `LangSpec` (node types for functions, classes, branches, nesting, loops, handlers, imports),
a name extractor in `parsers/treesitter.py`, and an extension mapping in `projects/discovery.py`.
Adding a metric: write a pass, register it in `analysis/registry.py`.
Adding a dataset: implement `DatasetAdapter` (`status`, `fetch`, `load`) and register it.

## Persistence
Plain files (no database): `workspaces/<id>/{meta.json, source/, analyses/*.json}`, `models/<id>/{model.joblib, manifest.json}`,
`experiments/<id>.json`, `datasets/raw|metadata`. Each analysis stores the config, pass results, snapshot hash and version;
the API reports an analysis as *stale* when the stored source no longer matches its hash.
Deleting a project deletes its whole directory. `joblib` files are loaded only from `models/`, which DefectScope itself writes.

## Jobs
In-process thread pool (2 workers). The UI polls `GET /api/jobs/{id}` and can `POST /api/jobs/{id}/cancel`. Jobs are lost on restart.

## Frontend
Hash-routed SPA. Code viewer is custom (highlight.js + fixed-height rows) rather than Monaco, to avoid a CDN dependency and to keep
per-line overlays simple. Charts and the treemap/graph layouts are hand-written SVG/CSS.

## Static-analysis providers (`analysis/diagnostics/`)
`DiagnosticProvider` subclasses (`python_tools.py`, `native_tools.py`) wrap one tool each and return `Diagnostic` objects
(tool, rule, severity, category, project-relative path, source range, message, CWE, enclosing entity, corroborating tools).
`categories.py` maps rule ids / CWEs to categories; unknown rules become "maintainability" rather than an invented bug type.
`run_tool()` runs without a shell, with a minimal environment and timeout. Each provider ignores project-supplied configuration
(`ruff --isolated`, an empty pylint rcfile, `clang-tidy --config={}`, explicit bandit/cppcheck options). Add a tool by writing a provider and
registering it in `registry.py`.

## Optional passes
A pass may raise `PassSkipped` (disabled, tool missing, no `.git`). The manager records it as "skipped" and provides `None` for its artifacts,
so downstream passes still run.

## History (`analysis/history/`)
`git_history.py` reads `git log --numstat` once (hooks and fsmonitor disabled, global/system config ignored) and aggregates per file.
`snapshots.py` measures complexity at sampled commits by reading blobs from Git objects; nothing is checked out or executed.
