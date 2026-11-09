import { useEffect, useState } from "react";
import { api, post } from "../api";
import { go } from "../App";
import type { Compat, Explanation, ModelSummary, PredictionDoc } from "../types/lab";
import type { ProjectCtx } from "../pages/ProjectPage";
import { HBars } from "../visualizations/charts";

interface CompatResp {
  analysis_id: string; functions_measured: number; languages_covered: string[]; unsupported_languages: Record<string, number>;
  models: { model: ModelSummary; compatibility: Compat }[];
}
type SortKey = "probability" | "cyclomatic" | "sloc" | "nesting_depth";

export default function RiskTab({ ctx }: { ctx: ProjectCtx }) {
  const { id, overview } = ctx;
  const [c, setC] = useState<CompatResp | null>(null);
  const [modelId, setModelId] = useState<string | null>(sessionStorage.getItem(`model:${id}`));
  const [doc, setDoc] = useState<PredictionDoc | null>(null);
  const [exp, setExp] = useState<Explanation | null>(null);
  const [sort, setSort] = useState<SortKey>("probability");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const aid = overview?.analysis_id;

  useEffect(() => { if (aid) api<CompatResp>(`/projects/${id}/model-compatibility`).then(setC); }, [id, aid]);
  useEffect(() => {
    setDoc(null); setExp(null);
    if (aid && modelId) api<PredictionDoc | null>(`/projects/${id}/predictions?model_id=${modelId}`).then(setDoc).catch(() => setDoc(null));
  }, [id, aid, modelId]);

  if (!overview) return <div className="page"><div className="panel empty"><h2>Run the analysis first</h2><p>Defect-risk estimates are built from the measured functions.</p></div></div>;

  const predict = async (mid: string) => {
    setBusy(true); setError(null); setExp(null);
    try {
      sessionStorage.setItem(`model:${id}`, mid); setModelId(mid);
      setDoc(await post<PredictionDoc>(`/projects/${id}/predict`, { model_id: mid }));
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const explain = async (entityId: string) => {
    if (!modelId) return;
    setExp(null);
    try { setExp(await post<Explanation>(`/projects/${id}/explain`, { model_id: modelId, entity_id: entityId })); } catch (e: any) { setError(e.message); }
  };

  const unsupported = c?.unsupported_languages ?? {};
  const rows = doc ? [...doc.predictions].sort((a, b) => (b[sort] ?? 0) - (a[sort] ?? 0)) : [];
  const th = (k: SortKey, label: string) => <th className="num" style={{ cursor: "pointer", color: sort === k ? "var(--ink)" : undefined }} onClick={() => setSort(k)}>{label}{sort === k ? " ↓" : ""}</th>;

  return (
    <div className="page grid">
      <div className="notice">
        <span className="badge layer-risk">predicted risk</span> A learned estimate of how similar a function's measurements are to defective modules in NASA projects. It is separate from the
        <span className="badge layer-structural" style={{ margin: "0 4px" }}>structural indicators</span> and is <b>not</b> a detection of a defect. Predictions are per function, never per line.
      </div>
      {error && <div className="notice error">{typeof error === "string" ? error.slice(0, 400) : "Error"}</div>}

      <div className="panel">
        <div className="panel-head"><h2>Which models can be applied here?</h2>
          <button className="btn small" onClick={() => go("/lab/models")}>Open model lab</button></div>
        <p className="small muted" style={{ marginBottom: 10 }}>{c?.functions_measured ?? 0} C/C++ functions were measured.
          {Object.keys(unsupported).length > 0 && ` ${Object.entries(unsupported).map(([l, n]) => `${n} ${l} functions`).join(", ")} have no applicable model: the NASA datasets contain no ${Object.keys(unsupported).join("/")} data, so DefectScope shows structural results only for them.`}</p>
        {!c ? <p className="muted small">Checking…</p> : c.models.length === 0 ? <div className="notice warn">No models exist yet. Train one under Model lab → Models.</div> : (
          <table className="t"><thead><tr><th>Model</th><th>Trained on</th><th className="num">CV AUC</th><th>Status</th><th /></tr></thead>
            <tbody>{c.models.map(({ model: m, compatibility: k }) => (
              <tr key={m.id}>
                <td>{m.name}</td><td>{m.training_projects.join(" + ")} <span className="faint">({m.supported_languages.map((l) => (l === "cpp" ? "C++" : "C")).join(", ")})</span></td>
                <td className="num">{m.cv_roc_auc?.toFixed(2) ?? "–"}</td>
                <td>{k.compatible ? <span className="badge" style={{ borderColor: "var(--ok)", color: "var(--ok)" }}>compatible · {k.predictable_rows} functions</span> : <span className="small" style={{ color: "var(--sev-high)" }}>{k.summary}</span>}</td>
                <td><button className="btn small primary" disabled={!k.compatible || busy} onClick={() => predict(m.id)}>{doc?.model.id === m.id ? "Re-run" : "Use"}</button></td>
              </tr>))}</tbody></table>
        )}
      </div>

      {doc && (
        <>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <div className="stat"><b>{doc.summary.predicted}</b><span>functions scored</span></div>
            <div className="stat"><b>{doc.summary.flagged}</b><span>above the model's threshold ({doc.model.decision_threshold.toFixed(2)})</span></div>
            <div className="stat"><b>{((doc.summary.mean_probability ?? 0) * 100).toFixed(0)}%</b><span>mean estimated risk (training rate {(doc.model.training_defect_rate * 100).toFixed(0)}%)</span></div>
            <div className="stat"><b>{doc.summary.with_out_of_range_features}</b><span>with metrics outside the training range</span></div>
          </div>
          {doc.compatibility.has_approximate_features && <div className="notice warn">Inputs are approximate re-measurements of the NASA metrics (different tokeniser and counting rules). Treat scores as a relative ranking, and treat absolute probabilities with caution.</div>}
          <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", alignItems: "start" }}>
            <div className="panel">
              <div className="panel-head"><h2>Review priority</h2><span className="small muted">click a column to sort · click a row to explain</span></div>
              <p className="small muted" style={{ marginBottom: 6 }}>Risk and structural measures are shown side by side rather than merged into one score.</p>
              <div style={{ overflowX: "auto" }}><table className="t">
                <thead><tr><th>Function</th>{th("probability", "Risk")}<th className="num">Pctl</th>{th("cyclomatic", "CC")}{th("sloc", "SLOC")}{th("nesting_depth", "Nest")}</tr></thead>
                <tbody>{rows.slice(0, 80).map((p) => (
                  <tr key={p.entity_id} className="click" onClick={() => explain(p.entity_id)} style={{ background: exp?.entity.id === p.entity_id ? "#f6dce1" : undefined }}>
                    <td><div>{p.name} {p.flagged && <span className="badge layer-risk">flagged</span>} {p.out_of_training_range.length > 0 && <span className="badge sev-warning" title={"Outside training range: " + p.out_of_training_range.join(", ")}>out of range</span>}</div>
                      <div className="small faint mono">{p.path}:{p.start_line}</div></td>
                    <td className="num"><b>{(p.probability * 100).toFixed(0)}%</b></td><td className="num">{p.percentile_in_project.toFixed(0)}</td>
                    <td className="num">{p.cyclomatic}</td><td className="num">{p.sloc}</td><td className="num">{p.nesting_depth}</td></tr>))}</tbody></table></div>
            </div>
            <div className="panel" style={{ position: "sticky", top: 56 }}>
              {!exp ? <><h2>Why this score?</h2><p className="small muted">Pick a function to see which measurements pushed its estimate up or down.</p>
                <h3 style={{ margin: "14px 0 6px" }}>Risk distribution</h3>
                <div className="hist" style={{ height: 90 }}>{doc.summary.probability_histogram.counts.map((n, i) => <div className="col" key={i}><em>{n || ""}</em><i style={{ height: `${(n / Math.max(1, ...doc.summary.probability_histogram.counts)) * 70}%`, background: "var(--risk)" }} /><span>{(doc.summary.probability_histogram.edges[i] * 100).toFixed(0)}</span></div>)}</div>
                <p className="small faint">estimated risk (%)</p></>
                : <>
                  <h2>{exp.entity.name}</h2>
                  <p className="small muted mono">{exp.entity.path}:{exp.entity.start_line}</p>
                  <p style={{ margin: "8px 0" }}>Estimated risk <b>{(exp.probability * 100).toFixed(0)}%</b> <span className="small muted">(threshold {(exp.threshold * 100).toFixed(0)}%)</span></p>
                  <HBars signed fmt={(v) => (v >= 0 ? "+" : "") + v.toFixed(3)} rows={exp.contributions.slice(0, 10).map((x) => ({
                    label: <span title={`value ${x.value} · training median ${x.training_median} · ${x.training_percentile.toFixed(0)}th percentile`}>{x.feature.replace("HALSTEAD_", "H_")} = {+x.value.toFixed(1)}</span>,
                    value: x.contribution, color: x.contribution >= 0 ? "var(--risk)" : "var(--history)" }))} />
                  <p className="small muted" style={{ marginTop: 8 }}>Bars show how each feature moved the model's {exp.space} from the training baseline ({exp.base_value?.toFixed(3)}). Red raises the score, teal lowers it.</p>
                  <details style={{ marginTop: 8 }}><summary className="small">Compared with the training population</summary>
                    <table className="t"><thead><tr><th>Feature</th><th className="num">Value</th><th className="num">Median</th><th className="num">Pctl</th></tr></thead>
                      <tbody>{exp.contributions.slice(0, 8).map((x) => <tr key={x.feature}><td className="small mono">{x.feature.replace("HALSTEAD_", "H_")}</td><td className="num">{+x.value.toFixed(1)}</td><td className="num">{+x.training_median.toFixed(1)}</td><td className="num">{x.training_percentile.toFixed(0)}</td></tr>)}</tbody></table></details>
                  <p className="small faint" style={{ marginTop: 8 }}>{exp.method}. {exp.caveat}</p>
                  <div className="row" style={{ marginTop: 8 }}><button className="btn small" onClick={() => ctx.open(exp.entity.path, exp.entity.start_line)}>Open in code viewer</button></div></>}
            </div>
          </div>
          <div className="panel"><h2>Read this carefully</h2><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{doc.caveats.map((x) => <li key={x}>{x}</li>)}</ul>
            <details style={{ marginTop: 8 }}><summary className="small">Feature availability for this model</summary>
              <table className="t"><thead><tr><th>Feature</th><th>Source on uploaded code</th><th>Note</th></tr></thead><tbody>{doc.compatibility.feature_table.map((f) => <tr key={f.feature}><td className="mono small">{f.feature}</td><td><span className={"badge" + (f.extraction === "approximate" ? " sev-warning" : "")}>{f.extraction}</span></td><td className="small muted">{f.caveat}</td></tr>)}</tbody></table></details></div>
        </>
      )}
    </div>
  );
}
