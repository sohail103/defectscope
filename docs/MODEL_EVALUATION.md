# Model evaluation

## Metrics reported
Accuracy, balanced accuracy, precision, recall, specificity, F1, ROC-AUC, PR-AUC, MCC, Brier score, confusion counts. Accuracy is deliberately listed last:
on PC1 (8% defective) a model that always predicts "clean" has ~92% accuracy and MCC 0.

## Example results (from this implementation)
These come from actual runs with seed 42, deduplicated D″ data, all 21 shared features, 5-fold stratified CV (one repeat). **Re-run them in the UI; do not treat these as
benchmarks.** Standard deviations are across folds, which are correlated.

ROC-AUC, within-project:

| | KC1 (C++) | PC1 (C) |
|---|---|---|
| Dummy | 0.500 | 0.500 |
| Logistic regression | 0.699 ± 0.030 | 0.866 ± 0.049 |
| Decision tree | 0.635 ± 0.044 | 0.777 ± 0.069 |
| Random forest | 0.721 ± 0.023 | 0.852 ± 0.046 |
| Gradient boosting | 0.713 ± 0.037 | 0.867 ± 0.032 |

Feature-group ablation (random forest, PC1, ROC-AUC): all 21 = 0.852; without size 0.792; without complexity 0.848; without Halstead 0.863;
only size 0.868; only complexity 0.637; only Halstead 0.777. Reading: size metrics carry most of the usable signal here; groups are heavily correlated, so removing one rarely hurts.

Pooled models trained on CM1+JM1+PC1 with the 18 measurable features (Platt-calibrated):
CV AUC ≈ 0.71 for logistic, forest and gradient boosting; leave-one-project-out AUC: CM1 0.69-0.70, JM1 0.66-0.68, PC1 0.79-0.82.
These LOPO numbers (not the CV figure) are the honest estimate for a new C project.

Dataset-level finding: in KC1 D″ the defect rate rises from 16% to 51% from the lowest to highest cyclomatic-complexity bin (association, not cause).

## Interpreting calibration
A model that is well ranked can still be badly calibrated. Probabilities are calibrated to the *training* defect rate; a project whose defect rate differs will not match.
Use predictions as a relative ranking unless you have validated calibration on comparable data.

## Reproducing
Each experiment JSON (`experiments/<id>.json`) stores config, seed, split settings, dataset checksums, library versions and all results.
Each model manifest stores hyperparameters, features, preprocessing, split definition, threshold, calibration, training statistics, CV and LOPO results.
