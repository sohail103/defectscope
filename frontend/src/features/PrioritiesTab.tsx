import { useEffect, useState } from "react";
import { api } from "../api";
import { go } from "../App";
import type { PriorityRow, Priorities } from "../types";
import type { ProjectCtx } from "../pages/ProjectPage";

type Key = "function_flag_count" | "cyclomatic" | "nesting_depth" | "diagnostics_high" | "file_commits" | "file_fix_commits" | "risk" | "sloc";
const FLAG_COLOR: Record<string, string> = { complexity: "layer-structural", duplication: "layer-structural", diagnostics: "layer-static", risk: "layer-risk", churn: "", fixes: "" };

export default function PrioritiesTab({ ctx }: { ctx: ProjectCtx }) {
  const [data, setData] = useState<Priorities | null>(null);
  const [sort, setSort] = useState<Key>("function_flag_count");
  const aid = ctx.overview?.analysis_id;
  const modelId = sessionStorage.getItem(`model:${ctx.id}`);
  useEffect(() => { if (aid) api<Priorities>(`/projects/${ctx.id}/priorities${modelId ? `?model_id=${modelId}` : ""}`).then(setData); }, [ctx.id, aid, modelId]);

  if (!ctx.overview) return <div className="page"><div className="panel empty"><h2>No analysis yet</h2><p>Run the analysis to rank functions for review.</p></div></div>;
  if (!data) return <div className="page muted">Loading…</div>;
  const val = (r: PriorityRow, k: Key) => (k === "function_flag_count" ? r.function_flag_count * 1000 + r.file_flag_count * 10 + (r.risk ?? 0) + r.cyclomatic / 1000 : (r[k] as number | null) ?? -1);
  const rows = [...data.rows].sort((a, b) => val(b, sort) - val(a, sort)).slice(0, 100);
  const th = (k: Key, label: string, title?: string) => <th className="num" title={title} style={{ cursor: "pointer", color: sort === k ? "var(--ink)" : undefined }} onClick={() => setSort(k)}>{label}{sort === k ? " ↓" : ""}</th>;
  const has = (f: string) => data.factors_available.includes(f);

  return (
    <div className="page grid">
      <div className="notice">{data.note}</div>
      {Object.entries(data.factors_unavailable).map(([k, v]) => (
        <div key={k} className="notice warn small">Factor not used ({k}): {v}. {k === "risk" && <button className="btn small" onClick={() => go(`/p/${ctx.id}/risk`)}>Open Defect risk</button>}</div>))}
      <div className="panel">
        <div className="panel-head"><h2>Where to look first</h2><span className="small muted">click a column to sort · click a row to open the code</span></div>
        <div style={{ overflowX: "auto" }}><table className="t">
          <thead><tr><th>Function</th>{th("function_flag_count", "Flags", "Sorted by function-level flags, then file-level flags")}
            {th("cyclomatic", "CC")}{th("nesting_depth", "Nest")}{th("sloc", "SLOC")}
            {has("diagnostics") && th("diagnostics_high", "High findings")}{has("churn") && th("file_commits", "File commits", "file-level")}{has("fixes") && th("file_fix_commits", "File fix-like", "file-level")}
            {has("risk") && th("risk", "Risk")}<th>Why it is listed</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.entity_id} className="click" onClick={() => ctx.open(r.path, r.start_line)}>
              <td><div>{r.name}</div><div className="small faint mono">{r.path}:{r.start_line}</div></td>
              <td className="num"><b>{r.function_flag_count}</b>{r.file_flag_count > 0 && <span className="faint"> +{r.file_flag_count}</span>}</td>
              <td className="num">{r.cyclomatic}</td><td className="num">{r.nesting_depth}</td><td className="num">{r.sloc}</td>
              {has("diagnostics") && <td className="num">{r.diagnostics_high || "·"}</td>}{has("churn") && <td className="num">{r.file_commits ?? "–"}</td>}{has("fixes") && <td className="num">{r.file_fix_commits ?? "–"}</td>}
              {has("risk") && <td className="num">{r.risk === null ? "–" : (r.risk * 100).toFixed(0) + "%"}</td>}
              <td>{r.flags.length === 0 ? <span className="faint">·</span> : r.flags.map((f) => <span key={f} className={"badge " + FLAG_COLOR[f]} style={{ marginRight: 4 }} title={data.labels[f]}>{f}</span>)}</td></tr>))}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>“+n” are file-level flags (churn, fix-like commits), which describe the whole file rather than this function.
          Thresholds (top 10%): {Object.entries(data.thresholds).map(([k, v]) => `${k} ≥ ${+v.toFixed(2)}`).join(", ") || "none"}.</p>
      </div>
    </div>
  );
}
