export type Language = "python" | "c" | "cpp";
export type Severity = "info" | "warning" | "high";
export type Layer = "structural" | "static_analysis" | "predicted_risk" | "historical";

export interface ProjectMeta {
  id: string; name: string; created_at: string; source: string; snapshot_hash: string;
  file_count: number; total_bytes: number;
  summary: {
    languages: Record<string, { files: number; bytes: number }>;
    analysable_files: number; excluded_files: number;
    excluded_directories: Record<string, string>; exclusion_reasons: Record<string, number>;
    build_systems: Record<string, string[]>; has_compile_commands: boolean;
    project_roots: string[]; source_directories: string[]; test_directories: string[];
    has_git: boolean; mixed_language: boolean; header_language_assumption: string | null;
    import_warnings: string[];
  };
}
export interface ProjectDetail { meta: ProjectMeta; latest_analysis: { analysis_id: string; created_at: string; stale: boolean } | null }

export interface TreeNode {
  name: string; path: string; type: "dir" | "file"; children?: TreeNode[];
  language?: Language | null; role?: string; size?: number; excluded?: string | null;
  max_cyclomatic?: number | null; hotspots?: number;
}
export interface Range { start_line: number; end_line: number; start_col: number; end_col: number }
export interface Entity {
  id: string; kind: "file" | "class" | "function"; name: string; qualified_name: string;
  language: Language; path: string; range: Range; parent_id: string | null; parent_scope: string | null;
  metrics: Record<string, number>; details: Record<string, any>;
}
export interface Hotspot {
  id: string; layer: Layer; entity_id: string; granularity: string; path: string; range: Range;
  rule: string; severity: Severity; value: number; threshold: number; message: string;
}
export interface PassResult { name: string; status: string; duration_s: number; message: string; warnings: string[] }
export interface Job {
  id: string; kind: string; project_id: string | null; status: string; progress: number;
  message: string; passes: PassResult[]; result: Record<string, any>; error: string | null;
}
export interface Histogram { label: string; count: number; min: number }
export interface Summary {
  totals: Record<string, number>;
  by_language: Record<string, Record<string, number>>;
  by_directory: Record<string, { files: number; sloc: number; functions: number; max_cyclomatic: number; hotspots: number }>;
  distributions: Record<string, Histogram[]>;
  hotspot_counts: { by_severity: Record<string, number>; by_rule: Record<string, number> };
  top_complex_functions: { id: string; name: string; path: string; start_line: number; cyclomatic: number; sloc: number; nesting_depth: number; parameters: number }[];
  top_files: { path: string; sloc: number; max_cyclomatic: number; functions: number; hotspots: number }[];
}
export interface AnalysisOverview {
  analysis_id: string; project_id: string; created_at: string; stale: boolean; analysis_version: string;
  passes: PassResult[]; discovery: ProjectMeta["summary"]; summary: Summary;
  capabilities: { analysis_level: string; semantic_analysis: boolean; note: string; tools_run?: string[] };
  tool_status: ToolStatus[]; diagnostics_summary: DiagnosticsSummary | null; has_history: boolean; clone_groups: number;
  history_brief: { commits_analysed: number; first_commit: string; last_commit: string; authors_total: number; fix_commits_total: number } | null;
  parse_status: Record<string, { ok: boolean; syntax_errors: number; level: string }>;
}
export interface Graph {
  nodes: { id: string; language: Language; fan_in: number; fan_out: number; in_cycle: boolean }[];
  edges: { source: string; target: string }[]; cycles: string[][]; external: Record<string, number>; note?: string;
}
export interface Diagnostic {
  id: string; tool: string; rule: string; severity: Severity; category: string; path: string; range: Range;
  message: string; entity_id: string | null; cwe: number | null; corroborated_by: string[];
}
export interface ToolStatus { tool: string; available: boolean; version: string | null; ran: boolean; files: number; findings: number; duration_s: number; notes: string[]; error: string | null }
export interface ToolInfo { name: string; description: string; languages: string[]; available: boolean; version: string | null; default_enabled: boolean; install_hint: string }
export interface DiagnosticsSummary { total: number; by_tool: Record<string, number>; by_severity: Record<string, number>; by_category: Record<string, number>; top_rules: { tool: string; rule: string; count: number }[]; files_with_findings: number }
export interface HistoryFile {
  git_commits: number; git_authors: number; git_added: number; git_deleted: number; git_churn: number; git_fix_commits: number; git_fix_ratio: number;
  git_change_entropy: number; git_days_since_last_change: number; git_age_days: number; git_top_author_share: number; git_recent_commits_90d: number;
  first_commit: string; last_commit: string;
}
export interface History {
  head: string; commits_analysed: number; truncated: boolean; first_commit: string; last_commit: string; reference_date: string; until: string | null;
  files: Record<string, HistoryFile>; monthly: { month: string; commits: number; churn: number; fix_commits: number; authors: number }[];
  contributors: { email: string; name: string; commits: number; churn: number }[]; authors_total: number; fix_commits_total: number;
  bugfix_keywords: string[]; notes: string[];
}
export interface ComplexityPoint {
  sha: string; date: string; subject: string; files: number; functions: number; sloc: number; total_cyclomatic: number; mean_cyclomatic: number;
  max_cyclomatic: number; high_complexity_functions: number; per_file_max_cyclomatic: Record<string, number>; capped: boolean;
}
export interface HistoryResponse { available: boolean; reason: string | null; history: History | null; complexity_history: { points: ComplexityPoint[]; tracked_files: string[]; note: string } | null }
export interface PriorityRow {
  entity_id: string; name: string; path: string; language: string; start_line: number; cyclomatic: number; nesting_depth: number; sloc: number;
  diagnostics_high: number | null; diagnostics_total: number | null; file_commits: number | null; file_fix_commits: number | null; file_churn: number | null;
  clone_group_size: number; risk: number | null; risk_flagged: boolean | null; flags: string[]; function_flag_count: number; file_flag_count: number;
}
export interface Priorities { rows: PriorityRow[]; factors_available: string[]; factors_unavailable: Record<string, string>; labels: Record<string, string>; thresholds: Record<string, number>; note: string }
export interface AnalysisConfig {
  static_analysis: { enabled: boolean; tools: string[]; timeout_s: number; max_files_per_tool: number };
  history: { enabled: boolean; max_commits: number; until: string | null; bugfix_keywords: string[]; complexity_samples: number };
  clones: { enabled: boolean; min_function_sloc: number; min_nodes: number };
  exclusions: {
    dirs: string[]; vendored_dirs: string[]; exclude_vendored: boolean; exclude_generated: boolean;
    exclude_tests: boolean; extra_globs: string[]; max_file_bytes: number;
  };
  thresholds: Record<string, number>;
  enabled_passes: string[] | null;
}
