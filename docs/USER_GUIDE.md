# User guide

## 1. Import a project
Home → **Choose ZIP**, drag a ZIP onto the box, **Choose folder**, or **Try the sample project**. For one file, paste it under *Analyse a single file*.
(Folder upload skips `node_modules`, virtualenvs and `__pycache__` in the browser; `.git` is kept.)
You land on the project overview, which lists what was found (languages, files, exclusions, build systems) before any analysis.

## 2. Configure and run
**Analysis setup** shows exclusions (vendored, generated, tests, custom globs, max file size), structural thresholds, and every pass with status and timing.
Click **Run analysis**. Progress shows in the top bar; you can cancel. Warnings (syntax errors, ambiguous class names...) appear under the pass list.

## 3. Read the overview
Statistics, distributions, the **project map** (area = SLOC, colour = highest cyclomatic complexity in the file), structural indicators and the most complex
functions. Click any row to open it in the code viewer.

## 4. Explorer
Left: file tree (chips show a file's highest complexity; excluded items are greyed with the reason). Centre: code with layers:
**complexity heat** (tint by function cyclomatic complexity), **structural flags** (left bar: yellow info, orange warning, rust high; hover for the reason),
**predicted risk** (triangle on a function's first line, only when a model has been applied). Click a line to select the enclosing function/class.
Right: the inspector shows why it was flagged, what adds to complexity (bars, and the contributing lines are highlighted), and all metrics.

## 5. Dependencies
Force-directed file graph (node size = fan-in, rust ring = in a cycle), cycle list, fan-in/out rankings, external dependencies.

## 6. Defect risk
1. Download data: **Model lab → Datasets → Download datasets**.
2. **Models → Train model**. Defaults (forest, CM1+JM1+PC1, 18 measurable features, Platt calibration) take about a minute. Inspect its evaluation and importance.
3. Open a project with C/C++ code → **Defect risk**. Models are listed with compatibility; click **Use**.
4. Click a function to see why it scored as it did. Red bars raise the estimate, teal bars lower it; values are compared with the training population.
Python functions never get a probability: there is no suitable training data. Structural results still apply.

## 7. Model lab
* **Datasets**: profile of each NASA project and version, duplicates, association of each metric with defects, which metrics are measurable on uploaded code.
* **Experiments**: pick B-F, configure, run (a few seconds to a few minutes), browse results. A is shown as unavailable with the reason.
* **Models**: train, inspect, delete.

## 8. Export
`GET /api/projects/{id}/export/metrics.csv?kind=function|class|file` and `/export/analysis.json` (also usable with curl). There are no HTML/PDF reports yet.

## 9. Deleting data
**Delete** on the home page removes a project and its analyses. Models: Models tab. Everything is plain files under the repo directory.
