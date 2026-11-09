# Datasets

## Implemented: NASA MDP (`NASAMDPAdapter`)
Source: https://github.com/klainfo/NASADefectDataset (a mirror of Shepperd et al.'s data). Projects used: **CM1, JM1, PC1 (C)** and **KC1 (C++)**.
Downloaded once to `datasets/raw/nasa_mdp/`; `datasets/metadata/nasa_mdp.json` records the archive and per-file SHA-256 and retrieval time.
Every model and experiment stores the file checksums it used.

Versions: `original`, `cleaned_Dprime` (D′), `cleaned_DDprime` (D″). **Default is D″.** Measured on the data:

| Project | Original rows | D″ rows | Defect rate (orig → D″) | Feature-identical duplicates (orig) |
|---|---|---|---|---|
| CM1 | 505 | 327 | 9.5% → 12.8% | 50 |
| JM1 | 10,878 | 7,720 | 19.3% → 20.9% | 2,061 |
| KC1 | 2,107 | 1,162 | 15.4% → 25.3% | 917 (44%) |
| PC1 | 1,107 | 679 | 6.9% → 8.1% | 152 |

Duplicates let near-copies fall on both sides of a random split, inflating scores. D″ has none.

### Schema
All four projects share 21 metrics with identical names (`LOC_*`, `CYCLOMATIC_COMPLEXITY`, `DESIGN_COMPLEXITY`, `ESSENTIAL_COMPLEXITY`,
`BRANCH_COUNT`, 12 Halstead values). CM1 and PC1 have additional metrics (call pairs, parameter count, ...) that JM1/KC1 lack,
so pooled models use the 21 shared ones. Rows are anonymous modules; there is no source code, no module names and no history.

### Compatibility with uploaded code
`features/schemas.py` states, for each metric, whether DefectScope can re-measure it:
* **approximate**: LOC_*, CYCLOMATIC_COMPLEXITY, operator/operand counts (different tokenisation from the NASA tool);
* **derived**: the other Halstead values (formulas verified against the data, e.g. error estimate = volume/3000, time = effort/18);
* **unavailable**: DESIGN_COMPLEXITY, ESSENTIAL_COMPLEXITY (need call-graph / structured reduction), BRANCH_COUNT (tool-specific; equals 2·v(g)−1 in ~95-97% of rows so it adds little).

Models trained with `mdp21` are marked *research only* and are never applied to uploaded code. Models trained with `mdp_extractable` (18 features) can be.

## Not implemented
* **Codeflaws** (C, buggy/fixed competition programs) and **BugsInPy** (Python buggy/fixed snapshots): no adapters yet. They are not tabular
  module-level datasets; BugsInPy file/function labels would need a documented derivation from fix commits and unchanged files are *not* confirmed clean.
* **LINE-DP** line-level data.
* Any dataset with development history, so the static-vs-history experiment cannot run (see METHODOLOGY).

## Adding an adapter
Implement `DatasetAdapter` in `backend/app/datasets/`, return `LoadedDataset` (features, labels, language, granularity, schema id, provenance, limitations), register in `registry.py`.
