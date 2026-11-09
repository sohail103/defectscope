# Methodology

## Research question and how each sub-question is addressed
| # | Question | Status |
|---|---|---|
| 1 | Association between complexity metrics and defect proneness | **Done**: Spearman ρ, Mann-Whitney effect size, BH-adjusted p-values, defect rate by quantile bin (Datasets tab) |
| 2 | Which structural characteristics are most informative | **Done**: permutation importance (held-out), feature-group ablation (Experiment E) |
| 3 | Do historical patterns add value beyond static metrics | **Not possible with current data** (Experiment A reports *unavailable*): NASA MDP has no history |
| 4 | How do algorithms compare | **Done**: Experiment B, identical splits |
| 5 | Performance on a different project | **Done**: Experiment C, leave-one-project-out, pairwise matrix, KS domain shift |
| 6 | Reliability of probabilities | **Done**: Experiment D, reliability curves, Brier, ECE, Platt/isotonic |
| 7 | Can predictions be explained | **Done**: SHAP (trees) / exact linear decomposition (logistic), local-accuracy checked |
| 8 | Localise suspicious modules/regions | Modules/functions: **done**. Lines: **not attempted** (no line-level labels or model) |
| 9 | Defects detectable by deterministic static analysis | **Not implemented** (no tool integration yet) |
| 10 | Effect of language/project | Partly: per-project results, C→C++ transfer via KC1; Python has no applicable data |

## Leakage controls
* Imputer, log transform, scaler live inside the sklearn `Pipeline` and are fit on training rows only, in every fold.
* Calibrators and decision thresholds are fit on **inner out-of-fold scores of the training fold**, never on held-out rows.
* No oversampling is used (class imbalance is reported, thresholds handle the trade-off). Outliers are reported, never removed.
* Default data is the deduplicated D″ version. Splits are stratified, seeded and repeated; folds from the same repeat are disjoint.
* Cross-project evaluation holds out *whole projects*.
* Caveat: D″ removes exact feature duplicates only. Near-duplicates may remain, so random-split results are still somewhat optimistic; prefer Experiment C numbers for generalisation.

## Decision threshold
Default strategy `oof_mcc`: pick the threshold maximising MCC on inner out-of-fold scores of the training set. Models are not trained with class weights by default,
so probabilities stay interpretable. The threshold table in Experiment B is descriptive (computed on held-out predictions; not used for tuning).

## Explanations
Global: permutation importance on held-out folds, coefficients (logistic), impurity importance (trees; flagged as biased). Local: SHAP `TreeExplainer`
(path-dependent) or exact linear contributions; each is checked for local accuracy (base + contributions = model output). Explanations are for the raw model score
before calibration (calibration is monotonic). **They describe what the model uses, not what causes defects.**

## Applying a model to a project
1. All features the model needs must be measurable (not `unavailable`) or the model is blocked.
2. Only functions in languages the model was trained on are scored; others are listed as excluded.
3. No missing values are filled; rows with missing values are skipped and reported.
4. Metrics outside the training range are flagged per function.
5. Output is per function only and is never converted to line-level scores.

## Not done (so they are not claimed)
Static-analysis integration, Git history features, line-level localisation (LINE-DP), Codeflaws/BugsInPy experiments, version comparison mode.
