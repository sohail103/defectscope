import { useEffect, useState } from "react";
import { api, fmt } from "../api";
import type { HistoryResponse } from "../types";
import type { ProjectCtx } from "../pages/ProjectPage";
import { Bars, LineChart } from "../visualizations/timeseries";

export default function HistoryTab({ ctx }: { ctx: ProjectCtx }) {
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [sort, setSort] = useState<"git_commits" | "git_churn" | "git_fix_commits" | "git_change_entropy">("git_commits");
  const aid = ctx.overview?.analysis_id;
  useEffect(() => { if (aid) api<HistoryResponse>(`/projects/${ctx.id}/history`).then(setData); }, [ctx.id, aid]);

  if (!ctx.overview) return <div className="page"><div className="panel empty"><h2>No analysis yet</h2><p>Run the analysis to read the project's Git history.</p></div></div>;
  if (!data) return <div className="page muted">Loading…</div>;
  if (!data.available || !data.history) {
    return (
      <div className="page"><div className="panel empty">
        <h2>No Git history in this analysis</h2><p>{data.reason}</p>
        <p style={{ marginTop: 8 }} className="small">History needs the project's <code>.git</code> folder. Import a ZIP or folder that includes it (hidden folders are included), and keep “History analysis” enabled under Analysis setup.</p>
      </div></div>
    );
  }
  const h = data.history, ch = data.complexity_history;
  const months = h.monthly.map((m) => m.month);
  const files = Object.entries(h.files).sort((a, b) => b[1][sort] - a[1][sort]).slice(0, 15);
  const th = (k: typeof sort, label: string) => <th className="num" style={{ cursor: "pointer", color: sort === k ? "var(--ink)" : undefined }} onClick={() => setSort(k)}>{label}{sort === k ? " ↓" : ""}</th>;

  return (
    <div className="page grid">
      <div className="notice" style={{ borderColor: "var(--history)", background: "#d9eeee" }}>
        <b>Development history</b> from Git, as of {h.reference_date}{h.until ? ` (cutoff ${h.until})` : ""}. Only commits up to that date are used, so these values are
        reproducible as of a past point and never include later changes. <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{h.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        <div className="stat"><b>{fmt(h.commits_analysed)}</b><span>commits ({h.first_commit} → {h.last_commit})</span></div>
        <div className="stat"><b>{h.authors_total}</b><span>contributors</span></div>
        <div className="stat"><b>{h.fix_commits_total}</b><span>fix-like commits (keyword heuristic)</span></div>
        <div className="stat"><b>{Object.keys(h.files).length}</b><span>files with history</span></div>
      </div>

      <div className="grid cols-2">
        <div className="panel"><h2>Commits per month</h2><p className="small muted" style={{ marginBottom: 6 }}>Red overlay: commits whose message looks like a bug fix.</p>
          <Bars labels={months} values={h.monthly.map((m) => m.commits)} overlay={h.monthly.map((m) => m.fix_commits)} /></div>
        <div className="panel"><h2>Code churn per month</h2><p className="small muted" style={{ marginBottom: 6 }}>Lines added plus deleted, in analysed and other files.</p>
          <Bars labels={months} values={h.monthly.map((m) => m.churn)} color="var(--static)" /></div>
      </div>

      {ch && ch.points.length > 1 && (
        <div className="panel">
          <div className="panel-head"><h2>Complexity over time</h2><span className="small muted">{ch.points.length} commits sampled evenly, read from Git objects</span></div>
          <div className="grid cols-2">
            <div><LineChart yLabel="cyclomatic complexity" labels={ch.points.map((p) => p.date.slice(2))} lines={[
              { name: "max", color: "#a63d17", values: ch.points.map((p) => p.max_cyclomatic) }, { name: "mean", color: "#a96a10", values: ch.points.map((p) => p.mean_cyclomatic) }]} />
              <div className="legend"><span><i className="key" style={{ width: 14, height: 3, background: "#a63d17", verticalAlign: 3 }} />highest function</span><span><i className="key" style={{ width: 14, height: 3, background: "#a96a10", verticalAlign: 3 }} />mean</span></div></div>
            <div><LineChart yLabel="functions / high-complexity functions" labels={ch.points.map((p) => p.date.slice(2))} lines={[
              { name: "functions", color: "#2c4fcf", values: ch.points.map((p) => p.functions) }, { name: "≥ threshold", color: "#a63d17", values: ch.points.map((p) => p.high_complexity_functions) }]} />
              <div className="legend"><span><i className="key" style={{ width: 14, height: 3, background: "#2c4fcf", verticalAlign: 3 }} />functions</span><span><i className="key" style={{ width: 14, height: 3, background: "#a63d17", verticalAlign: 3 }} />above the warning threshold</span></div></div>
          </div>
          <h3 style={{ margin: "14px 0 6px" }}>Evolution of the most complex files (max cyclomatic complexity)</h3>
          <div style={{ maxWidth: 760 }}><LineChart yLabel="file max complexity" labels={ch.points.map((p) => p.date.slice(2))} lines={ch.tracked_files.map((f, i) => ({ name: f, color: ["#a63d17", "#2c4fcf", "#1b7f7f", "#8f5fb0", "#a96a10"][i % 5], values: ch.points.map((p) => p.per_file_max_cyclomatic[f] ?? null) }))} /></div>
          <div className="legend">{ch.tracked_files.map((f, i) => <span key={f}><i className="key" style={{ width: 14, height: 3, background: ["#a63d17", "#2c4fcf", "#1b7f7f", "#8f5fb0", "#a96a10"][i % 5], verticalAlign: 3 }} />{f}</span>)}</div>
          <p className="small muted" style={{ marginTop: 8 }}>{ch.note}</p>
        </div>
      )}

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)", alignItems: "start" }}>
        <div className="panel"><h2>Most changed files</h2>
          <div style={{ overflowX: "auto" }}><table className="t"><thead><tr><th>File</th>{th("git_commits", "Commits")}<th className="num">Authors</th>{th("git_churn", "Churn")}{th("git_fix_commits", "Fix-like")}{th("git_change_entropy", "Entropy")}<th className="num">Idle (d)</th></tr></thead>
            <tbody>{files.map(([p, f]) => (
              <tr key={p} className="click" onClick={() => ctx.open(p)}><td className="mono small">{p}</td><td className="num">{f.git_commits}</td><td className="num">{f.git_authors}</td><td className="num">{fmt(f.git_churn)}</td><td className="num">{f.git_fix_commits}</td><td className="num">{f.git_change_entropy.toFixed(2)}</td><td className="num">{Math.round(f.git_days_since_last_change)}</td></tr>))}</tbody></table></div>
          <p className="small muted" style={{ marginTop: 6 }}>Entropy: how scattered the commits touching this file were across other files (higher = changes made alongside many files). Idle: days since the last change before the reference date.</p>
        </div>
        <div className="panel"><h2>Contributors</h2>
          <table className="t"><thead><tr><th>Author</th><th className="num">Commits</th><th className="num">Churn</th></tr></thead>
            <tbody>{h.contributors.map((c) => <tr key={c.email}><td>{c.name}</td><td className="num">{c.commits}</td><td className="num">{fmt(c.churn)}</td></tr>)}</tbody></table>
          <p className="small muted" style={{ marginTop: 6 }}>Authors are identified by e-mail; the same person using several addresses appears as several contributors.</p></div>
      </div>
    </div>
  );
}
