import { useEffect, useState } from "react";
import { api, pollJob, post } from "../api";
import type { Job } from "../types";
import type { AlgoInfo, DatasetStatus, ModelSummary } from "../types/lab";
import { HBars } from "../visualizations/charts";

export default function ModelsTab() {
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [algos, setAlgos] = useState<Record<string, AlgoInfo>>({});
  const [ds, setDs] = useState<DatasetStatus | null>(null);
  const [sel, setSel] = useState<any | null>(null);
  const [algo, setAlgo] = useState("forest");
  const [projects, setProjects] = useState<string[]>(["CM1", "JM1", "PC1"]);
  const [featureSet, setFeatureSet] = useState("mdp_extractable");
  const [calibration, setCalibration] = useState("sigmoid");
  const [seed, setSeed] = useState(42);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = !!job && ["queued", "running"].includes(job.status);
  const refresh = () => api<ModelSummary[]>("/models").then(setModels);
  useEffect(() => { refresh(); api<Record<string, AlgoInfo>>("/algorithms").then(setAlgos); api<DatasetStatus[]>("/datasets").then((d) => setDs(d[0])); }, []);

  const train = async () => {
    setError(null);
    try {
      const j = await post<Job>("/models/train", { algorithm: algo, projects, feature_set: featureSet, calibration, seed });
      setJob(j);
      const done = await pollJob(j.id, setJob, 800);
      if (done.status === "failed") setError(done.error ?? "Training failed");
      else setSel(await api(`/models/${done.result.model_id}`));
      refresh();
    } catch (e: any) { setError(e.message); }
  };
  const toggle = (p: string) => setProjects(projects.includes(p) ? projects.filter((x) => x !== p) : [...projects, p]);
  if (ds && !ds.present) return <div className="page"><div className="notice warn">Download the NASA datasets first (Model lab → Datasets).</div></div>;

  return (
    <div className="page grid" style={{ gridTemplateColumns: "340px minmax(0, 1fr)", alignItems: "start" }}>
      <div className="grid">
        <div className="panel">
          <h2>Train a model</h2>
          <div className="grid" style={{ gap: 10, marginTop: 6 }}>
            <label className="field">Algorithm<select className="input" value={algo} onChange={(e) => setAlgo(e.target.value)}>{Object.entries(algos).filter(([k]) => k !== "dummy").map(([k, a]) => <option key={k} value={k}>{a.label}</option>)}</select></label>
            <div><div className="small muted">Training projects</div><div className="row">{ds && Object.entries(ds.projects).map(([p, v]) => <label className="toggle" key={p}><input type="checkbox" checked={projects.includes(p)} onChange={() => toggle(p)} />{p} <span className="faint">({v.language === "cpp" ? "C++" : "C"})</span></label>)}</div></div>
            <label className="field">Features<select className="input" value={featureSet} onChange={(e) => setFeatureSet(e.target.value)}>
              <option value="mdp_extractable">Measurable on uploaded code (18)</option><option value="mdp21">All 21 shared metrics (research only)</option></select></label>
            <label className="field">Calibration<select className="input" value={calibration} onChange={(e) => setCalibration(e.target.value)}><option value="sigmoid">Platt scaling</option><option value="isotonic">Isotonic regression</option><option value="none">None</option></select></label>
            <label className="field">Seed<input className="input" type="number" value={seed} onChange={(e) => setSeed(+e.target.value)} /></label>
          </div>
          <p className="small muted" style={{ marginTop: 8 }}>A model only applies to languages it was trained on. Training evaluates it by cross-validation and leave-one-project-out, then fits the final model.</p>
          <div style={{ marginTop: 10 }}><button className="btn primary" disabled={running || projects.length === 0} onClick={train}>{running ? "Training…" : "Train model"}</button></div>
          {running && <div style={{ marginTop: 10 }}><div className="bar"><i style={{ width: `${(job?.progress ?? 0) * 100}%` }} /></div><p className="small muted" style={{ marginTop: 4 }}>{job?.message}</p></div>}
          {error && <div className="notice error" style={{ marginTop: 10 }}>{error}</div>}
        </div>
        <div className="panel">
          <h2>Registered models</h2>
          {models.length === 0 ? <p className="small muted">None yet.</p> : <div className="entlist">{models.map((m) => (
            <button key={m.id} className={"ent" + (sel?.id === m.id ? " sel" : "")} onClick={async () => setSel(await api(`/models/${m.id}`))}>
              <span className="nm">{m.name}</span>
              <span className={"badge " + (m.applicable_to_uploaded_code ? "" : "sev-high")}>{m.applicable_to_uploaded_code ? "usable" : "research"}</span></button>))}</div>}
        </div>
      </div>
      <div>{sel ? <ModelDetail m={sel} onDelete={async () => { if (!confirm("Delete this model?")) return; await api(`/models/${sel.id}`, { method: "DELETE" }); setSel(null); refresh(); }} />
        : <div className="panel empty"><h2>No model selected</h2><p>Train a model or pick one from the list to see its evaluation, explanations and limits.</p></div>}</div>
    </div>
  );
}

function ModelDetail({ m, onDelete }: { m: any; onDelete: () => void }) {
  const cv = m.evaluation.cross_validation.summary;
  const perm = m.global_explanations.permutation_importance_heldout as { feature: string; importance: number; std: number }[];
  const intr = m.global_explanations.intrinsic;
  const fmt = (x: any, d = 3) => (x ? `${x.mean.toFixed(d)} ± ${x.std.toFixed(d)}` : "–");
  return (
    <div className="grid">
      <div className="panel">
        <div className="panel-head"><h2>{m.name}</h2><button className="btn small danger" onClick={onDelete}>Delete</button></div>
        <dl className="kv small">
          <dt>Task</dt><dd>{m.task}</dd><dt>Algorithm</dt><dd>{m.algorithm_label}</dd><dt>Supported languages</dt><dd>{m.supported_languages.map((l: string) => l === "cpp" ? "C++" : l.toUpperCase()).join(", ")}{m.mixed_language_training ? " (mixed training)" : ""}</dd>
          <dt>Granularity</dt><dd>{m.granularity}</dd><dt>Features</dt><dd>{m.features.length} ({m.feature_set})</dd>
          <dt>Training data</dt><dd>{m.training_datasets.map((d: any) => d.id.split("/")[1]).join(" + ")} · {m.training_rows} rows · {(m.training_defect_rate * 100).toFixed(0)}% defective</dd>
          <dt>Calibration</dt><dd>{m.calibration}</dd><dt>Decision threshold</dt><dd>{m.decision_threshold.toFixed(3)} ({m.threshold_strategy})</dd><dt>Seed</dt><dd>{m.seed}</dd></dl>
        {m.applicable_to_uploaded_code ? <div className="notice" style={{ marginTop: 10 }}>This model only uses features DefectScope can measure on source code, so it can be applied to uploaded C/C++ projects.</div>
          : <div className="notice warn" style={{ marginTop: 10 }}>Research model: it needs {m.blocking_features.join(", ")}, which cannot be measured on uploaded code. It will never be applied to a project.</div>}
      </div>
      <div className="grid cols-2">
        <div className="panel"><h2>Estimated performance</h2>
          <p className="small muted" style={{ marginBottom: 6 }}>{m.evaluation.cross_validation.note}</p>
          <table className="t"><tbody>{["roc_auc", "pr_auc", "mcc", "balanced_accuracy", "recall", "precision", "brier"].map((k) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td className="num">{fmt(cv[k])}</td></tr>)}</tbody></table></div>
        <div className="panel"><h2>Leave-one-project-out</h2>
          {m.evaluation.leave_one_project_out.length === 0 ? <p className="small muted">Trained on one project, so there is no cross-project estimate.</p> : <table className="t"><thead><tr><th>Held out</th><th className="num">ROC-AUC</th><th className="num">MCC</th><th className="num">Recall</th></tr></thead>
            <tbody>{m.evaluation.leave_one_project_out.map((r: any) => <tr key={r.held_out}><td>{r.held_out} <span className="faint">({r.language === "cpp" ? "C++" : "C"})</span></td><td className="num">{r.metrics.roc_auc?.toFixed(3)}</td><td className="num">{r.metrics.mcc.toFixed(2)}</td><td className="num">{r.metrics.recall.toFixed(2)}</td></tr>)}</tbody></table>}</div>
      </div>
      <div className="grid cols-2">
        <div className="panel"><h2>Permutation importance</h2><p className="small muted" style={{ marginBottom: 8 }}>Drop in held-out ROC-AUC when a feature is shuffled. Predictive importance, not causation; correlated features share credit.</p>
          <HBars rows={perm.slice(0, 12).map((p) => ({ label: p.feature, value: Math.max(0, p.importance), err: p.std }))} /></div>
        <div className="panel"><h2>{intr.kind === "coefficients" ? "Model coefficients" : "Impurity importance"}</h2><p className="small muted" style={{ marginBottom: 8 }}>{intr.note}</p>
          <HBars rows={intr.values.slice(0, 12).map((p: any) => ({ label: p.feature, value: p.value }))} signed={intr.kind === "coefficients"} /></div>
      </div>
      <div className="panel"><h2>Limitations</h2><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{m.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul>
        <details style={{ marginTop: 8 }}><summary className="small">Preprocessing, split definition and provenance</summary>
          <ul className="small" style={{ paddingLeft: 18 }}>{m.preprocessing.map((p: string) => <li key={p}>{p}</li>)}<li>{m.split_definition}</li>
            {m.training_datasets.map((d: any) => <li key={d.id}>{d.id} {d.version} sha256 {String(d.sha256).slice(0, 16)}…</li>)}<li>scikit-learn {m.environment.scikit_learn}, numpy {m.environment.numpy}</li></ul></details></div>
    </div>
  );
}
