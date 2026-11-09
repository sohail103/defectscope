import { useEffect, useState } from "react";
import { api, bytes, fmt } from "../api";
import type { Entity, Hotspot } from "../types";
import type { ProjectCtx } from "../pages/ProjectPage";
import Histogram from "../visualizations/Histogram";
import Treemap, { ccColor } from "../visualizations/Treemap";

export default function OverviewTab({ ctx }: { ctx: ProjectCtx }) {
  const { overview, detail, id, open } = ctx;
  const [files, setFiles] = useState<Entity[]>([]);
  const [hot, setHot] = useState<Hotspot[]>([]);
  const aid = overview?.analysis_id;
  useEffect(() => {
    if (!aid) return;
    api<Entity[]>(`/projects/${id}/entities?kind=file&limit=5000`).then(setFiles);
    api<Hotspot[]>(`/projects/${id}/hotspots`).then(setHot);
  }, [id, aid]);

  const s = detail.meta.summary;
  if (!overview) {
    return (
      <div className="page grid">
        <div className="panel">
          <h2>Project discovered</h2>
          <p className="muted small" style={{ marginBottom: 12 }}>Nothing has been analysed yet. This is what was found on import.</p>
          <div className="grid cols-4">
            <div className="stat"><b>{s.analysable_files}</b><span>supported source files</span></div>
            <div className="stat"><b>{s.excluded_files}</b><span>files excluded</span></div>
            <div className="stat"><b>{Object.keys(s.languages).length}</b><span>languages: {Object.keys(s.languages).join(", ") || "none"}</span></div>
            <div className="stat"><b>{bytes(detail.meta.total_bytes)}</b><span>total size</span></div>
          </div>
          {s.import_warnings?.length > 0 && <div className="notice warn" style={{ marginTop: 12 }}>{s.import_warnings.slice(0, 3).join("; ")}</div>}
          <div style={{ marginTop: 16 }} className="row">
            <button className="btn primary" disabled={ctx.running || s.analysable_files === 0} onClick={ctx.run}>Run analysis</button>
            <span className="small muted">Review exclusions and thresholds first under “Analysis setup”.</span>
          </div>
          {s.analysable_files === 0 && <div className="notice warn" style={{ marginTop: 12 }}>No C, C++ or Python files were found after exclusions, so there is nothing to analyse.</div>}
        </div>
      </div>
    );
  }

  const t = overview.summary.totals;
  const d = overview.summary.distributions;
  const hc = overview.summary.hotspot_counts;
  const topHot = [...hot].sort((a, b) => ({ high: 0, warning: 1, info: 2 }[a.severity] - { high: 0, warning: 1, info: 2 }[b.severity]) || b.value - a.value).slice(0, 14);
  const failed = overview.passes.filter((p) => p.status === "failed");
  const badParse = Object.entries(overview.parse_status).filter(([, v]) => !v.ok);

  return (
    <div className="page grid">
      <div className="notice">
        <b>Analysis level: {overview.capabilities.analysis_level}.</b> {overview.capabilities.note} Highlights below are{" "}
        <span className="badge layer-structural">structural indicators</span> of complexity, not predicted defects.
      </div>
      {failed.length > 0 && <div className="notice error">Some passes failed: {failed.map((p) => `${p.name} (${p.message})`).join("; ")}</div>}
      {badParse.length > 0 && <div className="notice warn">{badParse.length} file(s) had syntax problems, so their metrics may be incomplete: {badParse.slice(0, 4).map(([p]) => p).join(", ")}{badParse.length > 4 ? "…" : ""}</div>}

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        <div className="stat"><b>{fmt(t.files)}</b><span>files analysed</span></div>
        <div className="stat"><b>{fmt(t.sloc)}</b><span>source lines</span></div>
        <div className="stat"><b>{fmt(t.functions)}</b><span>functions and methods</span></div>
        <div className="stat"><b>{fmt(t.classes)}</b><span>classes and structs</span></div>
        <div className="stat"><b>{fmt(t.mean_cyclomatic, 1)}</b><span>mean cyclomatic complexity</span></div>
        <div className="stat"><b>{fmt(t.max_cyclomatic)}</b><span>highest cyclomatic complexity</span></div>
      </div>

      <div className="grid cols-3">
        <div className="panel"><div className="panel-head"><h2>Cyclomatic complexity</h2><span className="small muted">functions</span></div><Histogram data={d.cyclomatic} /></div>
        <div className="panel"><div className="panel-head"><h2>Function length</h2><span className="small muted">SLOC</span></div><Histogram data={d.function_sloc} /></div>
        <div className="panel"><div className="panel-head"><h2>Nesting depth</h2><span className="small muted">levels</span></div><Histogram data={d.nesting_depth} /></div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Project map</h2>
          <div className="scale"><span>area = source lines · colour = highest cyclomatic complexity in the file</span>
            <span>low</span><span className="ramp" /><span>high</span></div>
        </div>
        <Treemap files={files.map((f) => ({ path: f.path, sloc: f.metrics.sloc ?? 0, cc: f.metrics.max_cyclomatic ?? 0 }))} onOpen={(p) => open(p)} />
      </div>

      <div className="grid cols-2">
        <div className="panel">
          <div className="panel-head"><h2>Structural indicators</h2>
            <span className="small muted">{Object.entries(hc.by_severity).map(([k, v]) => `${v} ${k}`).join(" · ") || "none"}</span></div>
          {topHot.length === 0 ? <p className="muted small">No function or class crossed the configured thresholds.</p> : (
            <table className="t"><tbody>
              {topHot.map((h) => (
                <tr key={h.id} className="click" onClick={() => open(h.path, h.range.start_line)}>
                  <td style={{ width: 70 }}><span className={"badge sev-" + h.severity}>{h.severity}</span></td>
                  <td><div>{h.message}</div><div className="small faint mono">{h.path}:{h.range.start_line}</div></td>
                </tr>
              ))}
            </tbody></table>
          )}
        </div>
        <div className="panel">
          <div className="panel-head"><h2>Most complex functions</h2></div>
          <table className="t">
            <thead><tr><th>Function</th><th className="num">CC</th><th className="num">SLOC</th><th className="num">Nest</th></tr></thead>
            <tbody>
              {overview.summary.top_complex_functions.slice(0, 12).map((f) => (
                <tr key={f.id} className="click" onClick={() => open(f.path, f.start_line)}>
                  <td><div>{f.name}</div><div className="small faint mono">{f.path}:{f.start_line}</div></td>
                  <td className="num"><span style={{ background: ccColor(f.cyclomatic), padding: "1px 6px", borderRadius: 3 }}>{f.cyclomatic}</span></td>
                  <td className="num">{f.sloc}</td><td className="num">{f.nesting_depth}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="panel">
          <h2>Languages</h2>
          <table className="t"><thead><tr><th>Language</th><th className="num">Files</th><th className="num">SLOC</th><th className="num">Functions</th><th className="num">Mean CC</th><th className="num">Max CC</th></tr></thead>
            <tbody>{Object.entries(overview.summary.by_language).map(([l, v]) => (
              <tr key={l}><td><span className={"lang " + l} />{l}</td><td className="num">{v.files}</td><td className="num">{fmt(v.sloc)}</td><td className="num">{v.functions}</td><td className="num">{v.mean_cyclomatic}</td><td className="num">{v.max_cyclomatic}</td></tr>
            ))}</tbody></table>
          <p className="small muted" style={{ marginTop: 8 }}>Languages are analysed with language-specific rules and are not mixed into one model.</p>
        </div>
        <div className="panel">
          <h2>Directories</h2>
          <table className="t"><thead><tr><th>Directory</th><th className="num">Files</th><th className="num">SLOC</th><th className="num">Max CC</th><th className="num">Flags</th></tr></thead>
            <tbody>{Object.entries(overview.summary.by_directory).sort((a, b) => b[1].max_cyclomatic - a[1].max_cyclomatic).slice(0, 10).map(([dir, v]) => (
              <tr key={dir}><td className="mono">{dir}</td><td className="num">{v.files}</td><td className="num">{fmt(v.sloc)}</td><td className="num">{v.max_cyclomatic}</td><td className="num">{v.hotspots}</td></tr>
            ))}</tbody></table>
        </div>
      </div>
    </div>
  );
}
