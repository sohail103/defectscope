import { Fragment } from "react";
import type { Entity, Hotspot } from "../types";

const LABELS: Record<string, string> = {
  loc: "Lines (physical)", sloc: "Source lines", comment_lines: "Comment lines", blank_lines: "Blank lines",
  parameters: "Parameters", local_variables: "Local variables", cyclomatic: "Cyclomatic complexity",
  cognitive: "Cognitive complexity (approx.)", nesting_depth: "Max nesting depth", branches: "Branches",
  loops: "Loops", returns: "Return statements", exception_handlers: "Exception handlers",
  logical_operators: "Logical operators", distinct_calls: "Distinct callees", pointer_ops: "Pointer operations",
  alloc_calls: "Resource acquisitions", free_calls: "Resource releases", goto_count: "goto statements",
  global_refs: "global/nonlocal uses", method_count: "Methods", field_count: "Fields",
  wmc: "WMC", dit: "DIT", noc: "NOC", cbo: "CBO (approx.)", rfc: "RFC (approx.)", lcom: "LCOM (approx.)",
  halstead_volume: "Halstead volume", halstead_difficulty: "Halstead difficulty", halstead_effort: "Halstead effort",
  function_count: "Functions", class_count: "Classes", imports: "Imports", fan_in: "Fan-in", fan_out: "Fan-out",
  instability: "Instability", external_dependencies: "External dependencies", max_cyclomatic: "Max cyclomatic",
  mean_cyclomatic: "Mean cyclomatic", avg_function_sloc: "Avg function SLOC", max_function_sloc: "Max function SLOC",
};
const SHOW: Record<string, string[]> = {
  function: ["sloc", "loc", "comment_lines", "parameters", "local_variables", "cyclomatic", "cognitive", "nesting_depth", "branches", "loops", "returns", "exception_handlers", "logical_operators", "distinct_calls", "pointer_ops", "alloc_calls", "free_calls", "goto_count", "global_refs", "halstead_volume", "halstead_difficulty", "halstead_effort"],
  class: ["sloc", "method_count", "field_count", "wmc", "dit", "noc", "cbo", "rfc", "lcom"],
  file: ["loc", "sloc", "comment_lines", "blank_lines", "function_count", "class_count", "imports", "max_cyclomatic", "mean_cyclomatic", "avg_function_sloc", "max_function_sloc", "fan_in", "fan_out", "instability", "external_dependencies"],
};

export default function Inspector({ file, entities, hotspots, selected, onSelect }: {
  file?: Entity; entities: Entity[]; hotspots: Hotspot[]; selected: Entity | null; onSelect: (e: Entity | null) => void;
}) {
  const e = selected ?? file ?? null;
  const list = entities.filter((x) => x.kind !== "file").sort((a, b) => a.range.start_line - b.range.start_line);
  const mine = e ? hotspots.filter((h) => (e.kind === "file" ? true : h.entity_id === e.id)) : [];
  const contrib = e?.details?.complexity_contributors as Record<string, number> | undefined;
  const cmax = contrib ? Math.max(1, ...Object.values(contrib)) : 1;

  return (
    <div className="inspector">
      {e ? (
        <>
          <h3 style={{ marginBottom: 2 }}>{e.kind === "file" ? e.name : e.qualified_name}</h3>
          <p className="small muted mono">{e.kind} · lines {e.range.start_line}–{e.range.end_line}{e.parent_scope ? ` · in ${e.parent_scope}` : ""}</p>
          {selected && <button className="btn small" style={{ marginTop: 6 }} onClick={() => onSelect(null)}>Back to file</button>}

          {mine.length > 0 && <>
            <h3>Why it is flagged</h3>
            <p className="small muted" style={{ marginBottom: 6 }}><span className="badge layer-structural">structural</span> Measured from the code's shape; not a prediction that a defect exists.</p>
            {mine.slice(0, 12).map((h) => (
              <div key={h.id} className={"hot " + h.severity}><b style={{ fontWeight: 500 }}>{h.rule.replace(/_/g, " ")}</b><div className="small">{h.message}</div>
                {e.kind === "file" && <div className="small faint mono">line {h.range.start_line}</div>}</div>
            ))}
          </>}

          {contrib && Object.keys(contrib).length > 0 && <>
            <h3>What adds to complexity</h3>
            <div className="grid" style={{ gap: 5 }}>
              {Object.entries(contrib).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <div className="mini" key={k}><span style={{ width: 96 }} className="mono">{k}</span><span className="track"><i style={{ width: `${(v / cmax) * 100}%` }} /></span><span className="mono">{v}</span></div>
              ))}
            </div>
            <p className="small faint" style={{ marginTop: 6 }}>Cyclomatic = 1 + the sum of these decision points. Highlighted lines in the code show where each occurs.</p>
          </>}

          <h3>Metrics</h3>
          <dl className="kv">
            {SHOW[e.kind].filter((k) => k in e.metrics).map((k) => <Fragment key={k}><dt>{LABELS[k] ?? k}</dt><dd>{e.metrics[k]}</dd></Fragment>)}
          </dl>
          {e.kind === "class" && e.details.oo_notes && <p className="small faint" style={{ marginTop: 8 }}>{e.details.oo_notes.approximation}</p>}
          {e.kind === "function" && e.language !== "python" && <p className="small faint" style={{ marginTop: 8 }}>Syntax-level only: macros are not expanded and calls are matched by name.</p>}
        </>
      ) : <p className="muted small">Run an analysis to see metrics for this file.</p>}

      {!selected && list.length > 0 && <>
        <h3>Classes and functions</h3>
        <div className="entlist">
          {list.map((x) => (
            <button key={x.id} className="ent" onClick={() => onSelect(x)}>
              <span className="nm" style={{ paddingLeft: x.kind === "function" && x.details.is_method ? 12 : 0 }}>{x.kind === "class" ? "◇ " : ""}{x.qualified_name}</span>
              <span className="mono small muted">{x.kind === "function" ? `cc ${x.metrics.cyclomatic}` : `wmc ${x.metrics.wmc ?? "–"}`}</span>
            </button>
          ))}
        </div>
      </>}
    </div>
  );
}
