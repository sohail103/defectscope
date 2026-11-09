# DefectScope

Explainable software defect prediction and code intelligence, running entirely on your machine.

Import a C, C++ or Python project, see where its structure gets complicated, and (for C/C++, where a validated
model applies) get an *estimated* module-level defect risk with an explanation of what drove it. A separate **Model
lab** trains and evaluates defect-prediction models on the real NASA MDP datasets.

Three kinds of finding are kept visually and conceptually separate everywhere in the UI:

| Layer | What it is | Where it appears |
|---|---|---|
| **Structural indicators** (ochre) | Measured complexity: cyclomatic complexity, nesting, length, parameters... | left gutter bar, heat tint |
| **Static-analysis findings** (blue) | Deterministic tool diagnostics. *Planned, not yet integrated.* | reserved gutter lane |
| **Predicted risk** (madder) | A learned, function-level estimate | right gutter lane, Defect risk tab |

Nothing is sent off your machine. Imported code is parsed, never executed.

## What works today

* **Import**: ZIP, folder, single file, or (opt-in) local path; secure extraction (path traversal, symlinks, size/ratio limits).
* **Discovery**: languages, test/source dirs, build systems, exclusions you can edit (vendored, generated, binary, large files).
* **Analysis passes** (declared inputs/outputs, dependency-resolved, cancellable): Tree-sitter parsing, symbol index with
  source ranges, line metrics, cyclomatic and cognitive complexity with per-construct contributors, nesting, Halstead,
  Chidamber-Kemerer OO metrics, file dependency graph (fan-in/out, cycles), structural hotspots, NASA-style feature extraction.
* **Explorer**: file tree, syntax-highlighted code viewer with layer toggles, per-function inspector explaining *why* code is flagged.
* **Overview**: distributions, project treemap (area = SLOC, colour = max complexity), directory/language tables, top hotspots.
* **Model lab**: NASA MDP download with checksums, dataset explorer, experiments B-F (algorithm comparison, leave-one-project-out,
  calibration, feature-group ablation, error analysis), model training with full manifests, permutation importance, SHAP.
* **Defect risk tab**: compatibility check, function-level predictions, local explanations, out-of-range flags.
* **Export**: metrics CSV and full analysis JSON.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for what is *not* implemented (static-analysis tools, Git history, Codeflaws/BugsInPy/LINE-DP, comparison mode, PDF/HTML reports, Experiment A).

## Quick start

Requires Python 3.11+ and Node 18+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
(cd frontend && npm install)
./scripts/dev.sh            # API on :8000, UI on http://127.0.0.1:5173
```

or build once and serve from one port: `./scripts/start.sh` then open http://127.0.0.1:8000.

First run: open the app, click **Try the sample project**, then **Run analysis**. For predictions, go to **Model lab → Datasets →
Download**, then **Models → Train model** (about a minute), then open a C/C++ project's **Defect risk** tab.

Tests: `cd backend && ../.venv/bin/python -m pytest -q`

Docs: [BUILD](docs/BUILD.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATASETS](docs/DATASETS.md) · [METRICS](docs/METRICS.md) ·
[METHODOLOGY](docs/METHODOLOGY.md) · [MODEL_EVALUATION](docs/MODEL_EVALUATION.md) · [USER_GUIDE](docs/USER_GUIDE.md) · [LIMITATIONS](docs/LIMITATIONS.md)
