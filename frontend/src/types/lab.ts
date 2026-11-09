export interface DatasetStatus {
  id: string; description: string; task: string; present: boolean; source: string;
  provenance: { source: string; archive_sha256: string; retrieved_at: string; files: Record<string, { sha256: string; bytes: number }> } | null;
  projects: Record<string, { language: string; domain: string }>; versions: string[]; default_version: string;
  common_features: string[]; limitations: string[];
}
export interface FeatureProfile {
  name: string; missing: number; min: number; median: number; mean: number; max: number; skew: number; constant: boolean;
  iqr_outliers: number; spearman_with_defect: number | null; mannwhitney_p: number | null; p_adjusted_bh: number | null;
  auc_effect: number | null; median_defective: number | null; median_clean: number | null;
}
export interface DatasetProfile {
  dataset_id: string; version: string; language: string; granularity: string; rows: number; n_features: number;
  defective: number; defect_rate: number; imbalance_ratio: number; missing_cells: number; duplicate_feature_rows: number;
  duplicate_fraction: number; conflicting_duplicate_rows: number; features: FeatureProfile[];
  high_correlation_pairs: { a: string; b: string; spearman: number }[]; branch_count_equals_2cc_minus_1: number | null;
  provenance: Record<string, any>; limitations: string[];
}
export interface Scatter { feature: string; points: { x: number; y: number }[]; bins: { range: string; n: number; defect_rate: number; median: number }[]; spearman: number | null; p: number | null; n: number; note: string }
export interface FeatureDef { name: string; group: string; description: string; extraction: string; source: string; caveat: string }
export interface AlgoInfo { label: string; defaults: Record<string, any>; allowed: string[] }
export interface ModelSummary {
  id: string; name: string; created_at: string; algorithm: string; algorithm_label: string; supported_languages: string[];
  feature_set: string; applicable_to_uploaded_code: boolean; blocking_features: string[]; calibration: string;
  decision_threshold: number; training_rows: number; training_defect_rate: number; mixed_language_training: boolean;
  n_features: number; training_projects: string[]; cv_roc_auc: number | null; lopo_roc_auc: (number | null)[];
}
export interface Metric { mean: number; std: number }
export type MetricSummary = Record<string, Metric | null>;
export interface ExperimentSummary { id: string; kind: string; title: string; status: string; created_at: string; duration_s: number; config: Record<string, any> }
export interface Experiment extends ExperimentSummary { results: any; environment: Record<string, string> }
export interface Prediction {
  entity_id: string; path: string; name: string; language: string; start_line: number; end_line: number; probability: number;
  flagged: boolean; percentile_in_project: number; out_of_training_range: string[]; cyclomatic: number | null; sloc: number | null; nesting_depth: number | null;
}
export interface Compat {
  compatible: boolean; summary: string; reasons: string[]; predictable_rows: number; excluded_by_language: Record<string, number>;
  feature_table: { feature: string; available: boolean; extraction: string; caveat: string; group: string }[]; has_approximate_features?: boolean;
}
export interface PredictionDoc {
  model: { id: string; name: string; algorithm_label: string; calibration: string; decision_threshold: number; training_defect_rate: number; training_projects: string[] };
  compatibility: Compat; granularity: string; caveats: string[]; predictions: Prediction[];
  summary: { predicted: number; flagged: number; mean_probability: number | null; with_out_of_range_features: number; excluded_by_language: Record<string, number>; probability_histogram: { counts: number[]; edges: number[] } };
}
export interface Explanation {
  method: string; space?: string; base_value?: number; raw_score: number; probability: number; threshold: number; note: string; caveat?: string;
  local_accuracy_error?: number | null; entity: { id: string; name: string; path: string; start_line: number };
  contributions: { feature: string; value: number; contribution: number; training_percentile: number; training_median: number; outside_training_range: boolean }[];
}
