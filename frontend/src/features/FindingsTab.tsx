import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Diagnostic, DiagnosticsSummary, ToolStatus } from "../types";
import type { ProjectCtx } from "../pages/ProjectPage";

interface Resp { total: number; items: Diagnostic[]; summary: DiagnosticsSummary | null; tools: ToolStatus[] }
const pretty = (s: string) => s.replace(/_/g, " ");

export default function FindingsTab({ ctx }: { ctx: ProjectCtx }) {
  const [data, setData] = useState<Resp | null>(null);
  const [tool, setTool] = useState(""), [category, setCategory] = useState(""), [severity, setSeverity] = useState("");
  const aid = ctx.overview?.analysis_id;
  useEffect(() => { if (aid) api<Resp>(`/projects/${ctx.id}/diagnostics?limit=5000`).then(setData); }, [ctx.id, aid]);
  const items = useMemo(() => (data?.items ?? []).filter((d) => (!tool || d.tool === tool) && (!category || d.category === category) && (!severity || d.severity === severity)), [data, tool, category, severity]);

  if (!ctx.overview) return <div className="page"><div className="panel empty"><h2>No analysis yet</h2><p>Run the analysis to run the static-analysis tools.</p></div></div>;
  if (!data) return <div className="page muted">Loading…</div>;
  const sum = data.summary;
  const notRun = data.tools.filter((t) => !t.ran);

  return (
    <div className="page grid">
      <div className="notice" style={{ borderColor: "var(--static)" }}>
        <span className="badge layer-static">static analysis</span> Findings from deterministic tools that inspect the code without running it. They are separate from the
        <span className="badge layer-structural" style={{ margin: "0 4px" }}>structural indicators</span> and from <span className="badge layer-risk">predicted risk</span>.
        A finding is a rule violation the tool believes is real; it can still be a false positive.
      </div>

      {sum && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
          <div className="stat"><b>{sum.total}</b><span>findings in {sum.files_with_findings} files</span></div>
          <div className="stat"><b style={{ color: "var(--sev-high)" }}>{sum.by_severity.high ?? 0}</b><span>high severity</span></div>
          <div className="stat"><b>{sum.by_severity.warning ?? 0}</b><span>warnings</span></div>
          <div className="stat"><b>{sum.by_severity.info ?? 0}</b><span>informational</span></div>
        </div>
      )}

      <div className="grid cols-2">
        <div className="panel">
          <h2>By category</h2>
          {sum && Object.keys(sum.by_category).length ? (
            <div className="grid" style={{ gap: 4, marginTop: 6 }}>
              {Object.entries(sum.by_category).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <button key={k} className="ent" style={{ background: category === k ? "var(--static-tint)" : undefined }} onClick={() => setCategory(category === k ? "" : k)}>
                  <span className="nm">{pretty(k)}</span><span className="mono small">{v}</span></button>))}
            </div>
          ) : <p className="muted small">No findings.</p>}
        </div>
        <div className="panel">
          <h2>Tools</h2>
          <table className="t"><thead><tr><th>Tool</th><th>Status</th><th className="num">Findings</th><th className="num">Time</th></tr></thead>
            <tbody>{data.tools.map((t) => (
              <tr key={t.tool} title={t.notes.join("\n")}>
                <td>{t.tool} <span className="faint small">{t.version?.replace(/^.*?(\d)/, "$1")}</span></td>
                <td>{t.ran ? <span className="badge" style={{ borderColor: "var(--ok)", color: "var(--ok)" }}>ran</span> : <span className="badge sev-warning">{t.available ? "no files" : "not installed"}</span>}</td>
                <td className="num"><button className="btn small" style={{ border: 0, background: tool === t.tool ? "var(--static-tint)" : "none" }} onClick={() => setTool(tool === t.tool ? "" : t.tool)}>{t.findings}</button></td>
                <td className="num">{t.duration_s ? t.duration_s + "s" : ""}</td></tr>))}</tbody></table>
          {data.tools.flatMap((t) => t.notes.filter((n) => !n.startsWith("Not installed")).map((n) => <p key={t.tool + n} className="small muted" style={{ marginTop: 4 }}><b>{t.tool}:</b> {n}</p>))}
          {notRun.some((t) => !t.available) && <p className="small muted" style={{ marginTop: 6 }}>Missing tools can be installed (see Analysis setup) and the analysis re-run.</p>}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><h2>Findings ({items.length})</h2>
          <div className="row">
            <select className="input" style={{ width: 130 }} value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">all severities</option><option value="high">high</option><option value="warning">warning</option><option value="info">info</option></select>
            <select className="input" style={{ width: 160 }} value={tool} onChange={(e) => setTool(e.target.value)}><option value="">all tools</option>{Object.keys(sum?.by_tool ?? {}).map((t) => <option key={t}>{t}</option>)}</select>
            <select className="input" style={{ width: 190 }} value={category} onChange={(e) => setCategory(e.target.value)}><option value="">all categories</option>{Object.keys(sum?.by_category ?? {}).map((t) => <option key={t} value={t}>{pretty(t)}</option>)}</select>
            {(tool || category || severity) && <button className="btn small" onClick={() => { setTool(""); setCategory(""); setSeverity(""); }}>Clear</button>}
          </div></div>
        {items.length === 0 ? <p className="muted small">No findings match.</p> : (
          <div style={{ overflowX: "auto" }}><table className="t">
            <thead><tr><th>Severity</th><th>Finding</th><th>Category</th><th>Tool</th><th>Location</th></tr></thead>
            <tbody>{items.slice(0, 400).map((d) => (
              <tr key={d.id} className="click" onClick={() => ctx.open(d.path, d.range.start_line)}>
                <td><span className={"badge sev-" + d.severity}>{d.severity}</span></td>
                <td><div>{d.message}</div><div className="small faint mono">{d.rule}{d.cwe ? ` · CWE-${d.cwe}` : ""}</div></td>
                <td>{pretty(d.category)}</td>
                <td>{d.tool}{d.corroborated_by.length > 0 && <div className="small" style={{ color: "var(--static)" }} title="Other tools reported the same kind of issue on this line">also: {d.corroborated_by.join(", ")}</div>}</td>
                <td className="mono small">{d.path}:{d.range.start_line}</td></tr>))}</tbody></table></div>)}
        {items.length > 400 && <p className="small muted" style={{ marginTop: 6 }}>Showing the first 400. Use the filters to narrow down.</p>}
      </div>
    </div>
  );
}
