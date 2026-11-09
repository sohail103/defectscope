import { useEffect, useState } from "react";
import { api, pollJob, post } from "../api";
import type { Job } from "../types";
import type { AlgoInfo, DatasetStatus, Experiment, ExperimentSummary } from "../types/lab";
import ExperimentResults, { ALGO_COLOR } from "./ExperimentResults";

const MULTI = new Set(["algorithm_comparison", "cross_project"]);
const FOCUS_ALGO = new Set(["ablation", "error_analysis"]);
const FOCUS_PROJ = new Set(["calibration", "ablation", "error_analysis"]);
const USES_ALGOS = new Set(["algorithm_comparison", "cross_project", "calibration"]);

export default function ExperimentsTab() {
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [algos, setAlgos] = useState<Record<string, AlgoInfo>>({});
  const [ds, setDs] = useState<DatasetStatus | null>(null);
  const [past, setPast] = useState<ExperimentSummary[]>([]);
  const [kind, setKind] = useState("algorithm_comparison");
  const [projects, setProjects] = useState<string[]>(["CM1", "JM1", "KC1", "PC1"]);
  const [algoSel, setAlgoSel] = useState<string[]>(["dummy", "logistic", "tree", "forest", "gboost"]);
  const [focusAlgo, setFocusAlgo] = useState("forest");
  const [focusProj, setFocusProj] = useState("JM1");
  const [featureSet, setFeatureSet] = useState("mdp21");
  const [version, setVersion] = useState("cleaned_DDprime");
  const [seed, setSeed] = useState(42);
  const [splits, setSplits] = useState(5);
  const [repeats, setRepeats] = useState(2);
  const [job, setJob] = useState<Job | null>(null);
  const [exp, setExp] = useState<Experiment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const running = !!job && ["queued", "running"].includes(job.status);

  const refresh = () => api<ExperimentSummary[]>("/experiments").then(setPast);
  useEffect(() => {
    api<Record<string, string>>("/experiment-kinds").then(setKinds);
    api<Record<string, AlgoInfo>>("/algorithms").then(setAlgos);
    api<DatasetStatus[]>("/datasets").then((d) => setDs(d[0]));
    refresh();
  }, []);

  const toggle = (arr: string[], v: string, set: (a: string[]) => void) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const run = async () => {
    setError(null); setExp(null);
    try {
      const j = await post<Job>("/experiments", { kind, projects, version, feature_set: featureSet, algorithms: algoSel, seed, n_splits: splits, n_repeats: repeats,
        focus_algorithm: focusAlgo, focus_project: focusProj });
      setJob(j);
      const done = await pollJob(j.id, setJob, 700);
      if (done.status === "failed") setError(done.error ?? "Experiment failed");
      else if (done.result.experiment_id) setExp(await api<Experiment>(`/experiments/${done.result.experiment_id}`));
      refresh();
    } catch (e: any) { setError(e.message); }
  };

  if (ds && !ds.present) return <div className="page"><div className="notice warn">Download the NASA datasets first (Model lab → Datasets).</div></div>;
  const projNames = ds ? Object.keys(ds.projects) : [];
  const ok = (MULTI.has(kind) ? projects.length >= (kind === "cross_project" ? 2 : 1) : true) && (!USES_ALGOS.has(kind) || algoSel.length > 0);

  return (
    <div className="page grid" style={{ gridTemplateColumns: "340px minmax(0, 1fr)", alignItems: "start" }}>
      <div className="grid">
        <div className="panel">
          <h2>Experiment</h2>
          <div className="grid" style={{ gap: 6, marginTop: 6 }}>
            {Object.entries(kinds).map(([k, t]) => (
              <label className="toggle" key={k}><input type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} />{t}</label>))}
          </div>
        </div>
        <div className="panel">
          <h2>Configuration</h2>
          <div className="grid" style={{ gap: 10, marginTop: 6 }}>
            {MULTI.has(kind) && <div><div className="small muted">Projects</div><div className="row">{projNames.map((p) => <label className="toggle" key={p}><input type="checkbox" checked={projects.includes(p)} onChange={() => toggle(projects, p, setProjects)} />{p}</label>)}</div></div>}
            {FOCUS_PROJ.has(kind) && <label className="field">Project<select className="input" value={focusProj} onChange={(e) => setFocusProj(e.target.value)}>{projNames.map((p) => <option key={p}>{p}</option>)}</select></label>}
            {USES_ALGOS.has(kind) && <div><div className="small muted">Algorithms</div><div className="row">{Object.entries(algos).map(([k, a]) => <label className="toggle" key={k} title={JSON.stringify(a.defaults)}><input type="checkbox" checked={algoSel.includes(k)} onChange={() => toggle(algoSel, k, setAlgoSel)} /><i style={{ width: 8, height: 8, borderRadius: 2, background: ALGO_COLOR[k] }} />{k}</label>)}</div></div>}
            {FOCUS_ALGO.has(kind) && <label className="field">Algorithm<select className="input" value={focusAlgo} onChange={(e) => setFocusAlgo(e.target.value)}>{Object.entries(algos).filter(([k]) => k !== "dummy").map(([k, a]) => <option key={k} value={k}>{a.label}</option>)}</select></label>}
            <label className="field">Feature set<select className="input" value={featureSet} onChange={(e) => setFeatureSet(e.target.value)}><option value="mdp21">All 21 shared NASA metrics (research)</option><option value="mdp_extractable">Metrics measurable on uploaded code</option></select></label>
            <label className="field">Data version<select className="input" value={version} onChange={(e) => setVersion(e.target.value)}>{(ds?.versions ?? []).map((v) => <option key={v}>{v}</option>)}</select></label>
            <div className="row"><label className="field" style={{ width: 80 }}>Seed<input className="input" type="number" value={seed} onChange={(e) => setSeed(+e.target.value)} /></label>
              <label className="field" style={{ width: 80 }}>Folds<input className="input" type="number" min={2} max={10} value={splits} onChange={(e) => setSplits(+e.target.value)} /></label>
              <label className="field" style={{ width: 80 }}>Repeats<input className="input" type="number" min={1} max={5} value={repeats} onChange={(e) => setRepeats(+e.target.value)} /></label></div>
          </div>
          <div style={{ marginTop: 12 }}><button className="btn primary" disabled={running || !ok} onClick={run}>{running ? "Running…" : "Run experiment"}</button></div>
          {version === "original" && <p className="small" style={{ marginTop: 8, color: "var(--sev-high)" }}>The original data has many duplicate rows; scores will be optimistic.</p>}
        </div>
        {past.length > 0 && <div className="panel"><h2>Previous runs</h2><div className="entlist">{past.slice(0, 12).map((p) => (
          <button key={p.id} className="ent" onClick={async () => { setExp(await api<Experiment>(`/experiments/${p.id}`)); }}><span className="nm">{p.title.slice(0, 34)}</span><span className="small muted">{new Date(p.created_at).toLocaleDateString()}</span></button>))}</div></div>}
      </div>

      <div>
        {running && <div className="panel"><h2>Running</h2><div className="bar" style={{ margin: "8px 0" }}><i style={{ width: `${(job?.progress ?? 0) * 100}%` }} /></div><p className="small muted">{Math.round((job?.progress ?? 0) * 100)}% · {job?.message}</p>
          <button className="btn small" style={{ marginTop: 8 }} onClick={() => job && post(`/jobs/${job.id}/cancel`)}>Cancel</button></div>}
        {error && <div className="notice error">{error}</div>}
        {exp ? <ExperimentResults exp={exp} /> : !running && <div className="panel empty"><h2>Choose an experiment</h2><p>Every number shown here comes from fitting real models on the downloaded datasets.</p></div>}
      </div>
    </div>
  );
}
