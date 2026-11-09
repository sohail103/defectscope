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
  capabilities: { analysis_level: string; semantic_analysis: boolean; note: string };
  parse_status: Record<string, { ok: boolean; syntax_errors: number; level: string }>;
}
export interface Graph {
  nodes: { id: string; language: Language; fan_in: number; fan_out: number; in_cycle: boolean }[];
  edges: { source: string; target: string }[]; cycles: string[][]; external: Record<string, number>; note?: string;
}
export interface AnalysisConfig {
  exclusions: {
    dirs: string[]; vendored_dirs: string[]; exclude_vendored: boolean; exclude_generated: boolean;
    exclude_tests: boolean; extra_globs: string[]; max_file_bytes: number;
  };
  thresholds: Record<string, number>;
  enabled_passes: string[] | null;
}
