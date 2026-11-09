import { useState } from "react";
import type { Experiment } from "../types/lab";
import { CurvePlot, HBars, Legend } from "../visualizations/charts";

export const ALGO_COLOR: Record<string, string> = { dummy: "#8a95a0", logistic: "#2c4fcf", tree: "#a96a10", forest: "#2f7d4f", gboost: "#a8223b" };
const pm = (m: any, d = 3) => (m ? `${m.mean.toFixed(d)} ± ${m.std.toFixed(d)}` : "–");
const f3 = (v: number | null | undefined, d = 3) => (v === null || v === undefined ? "–" : v.toFixed(d));

export default function ExperimentResults({ exp }: { exp: Experiment }) {
  const r = exp.results;
  return (
    <div className="grid">
      <div className="panel">
        <div className="panel-head"><h2>{exp.title}</h2><span className="small muted">{new Date(exp.created_at).toLocaleString()} · {exp.duration_s}s</span></div>
        <p className="small muted">seed {exp.config.seed} · {exp.config.n_splits}-fold × {exp.config.n_repeats} · features {exp.config.feature_set} · data {exp.config.version}{" "}
          · scikit-learn {exp.environment.scikit_learn}</p>
        {(r.datasets ?? []).length > 0 && <p className="small muted" style={{ marginTop: 4 }}>Datasets: {r.datasets.map((d: any) => `${d.id.split("/")[1]} (${d.rows} rows, ${(d.defect_rate * 100).toFixed(0)}% defective, sha ${String(d.sha256).slice(0, 8)})`).join(" · ")}</p>}
      </div>
      {exp.status === "unavailable" && <div className="notice warn"><b>Not run.</b> {r.reason}<br /><span className="small">Needed: {r.needed}</span></div>}
      {exp.kind === "algorithm_comparison" && <Comparison r={r} />}
      {exp.kind === "cross_project" && <CrossProject r={r} />}
      {exp.kind === "calibration" && <Calibration r={r} />}
      {exp.kind === "ablation" && <Ablation r={r} />}
      {exp.kind === "error_analysis" && <ErrorAnalysis r={r} />}
      {(r.notes ?? []).length > 0 && <div className="notice"><b>How to read this.</b><ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>{r.notes.map((n: string) => <li key={n}>{n}</li>)}</ul></div>}
    </div>
  );
}

function Comparison({ r }: { r: any }) {
  const projects = Object.keys(r.per_project);
  const [proj, setProj] = useState(projects[0]);
  const rows = r.per_project[proj] as any[];
  const [algo, setAlgo] = useState("forest");
  const sel = rows.find((x) => x.algorithm === algo) ?? rows[0];
  return (
    <>
      <div className="row">{projects.map((p) => <button key={p} className={"btn" + (p === proj ? " primary" : "")} onClick={() => setProj(p)}>{p}</button>)}</div>
      <div className="panel">
        <h2>Held-out performance on {proj} <span className="small muted">(mean ± std over folds)</span></h2>
        <div style={{ overflowX: "auto" }}><table className="t">
          <thead><tr><th>Algorithm</th><th className="num">ROC-AUC</th><th className="num">PR-AUC</th><th className="num">MCC</th><th className="num">Balanced acc.</th><th className="num">F1</th><th className="num">Recall</th><th className="num">Precision</th><th className="num">Specificity</th><th className="num">Brier</th><th className="num">Accuracy</th></tr></thead>
          <tbody>{rows.map((x) => (
            <tr key={x.algorithm} className="click" onClick={() => setAlgo(x.algorithm)} style={{ background: x.algorithm === sel.algorithm ? "#f1f4f0" : undefined }}>
              <td><i style={{ display: "inline-block", width: 10, height: 10, background: ALGO_COLOR[x.algorithm], borderRadius: 2, marginRight: 6 }} />{x.label}</td>
              {["roc_auc", "pr_auc", "mcc", "balanced_accuracy", "f1", "recall", "precision", "specificity", "brier", "accuracy"].map((k) => <td key={k} className="num">{pm(x.summary[k])}</td>)}
            </tr>))}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>Accuracy is shown last on purpose: with {(rows[0].pooled_oof_repeat0.prevalence * 100).toFixed(0)}% defective modules, a model that predicts “clean” for everything scores {((1 - rows[0].pooled_oof_repeat0.prevalence) * 100).toFixed(0)}% accuracy. Compare MCC, PR-AUC and balanced accuracy.</p>
      </div>
      <div className="grid cols-2">
        <div className="panel"><h2>ROC curve (pooled out-of-fold, repeat 1)</h2>
          <CurvePlot diagonal xLabel="False positive rate" yLabel="True positive rate" series={rows.map((x) => ({ name: x.label, color: ALGO_COLOR[x.algorithm], points: x.curves.roc }))} />
          <Legend items={rows.map((x) => ({ name: x.label, color: ALGO_COLOR[x.algorithm] }))} /></div>
        <div className="panel"><h2>Precision–recall curve</h2>
          <CurvePlot xLabel="Recall" yLabel="Precision" series={rows.map((x) => ({ name: x.label, color: ALGO_COLOR[x.algorithm], points: x.curves.pr }))} /></div>
      </div>
      <div className="panel">
        <div className="panel-head"><h2>Threshold trade-off: {sel.label}</h2><span className="small muted">pooled out-of-fold predictions on {proj}; descriptive, not tuned</span></div>
        <div style={{ overflowX: "auto" }}><table className="t"><thead><tr><th className="num">Threshold</th><th className="num">Recall</th><th className="num">Precision</th><th className="num">Specificity</th><th className="num">MCC</th><th className="num">Missed defects (FN)</th><th className="num">False alarms (FP)</th></tr></thead>
          <tbody>{sel.threshold_table.filter((_: any, i: number) => i % 2 === 0).map((t: any) => <tr key={t.threshold}><td className="num">{t.threshold.toFixed(2)}</td><td className="num">{f3(t.recall, 2)}</td><td className="num">{f3(t.precision, 2)}</td><td className="num">{f3(t.specificity, 2)}</td><td className="num">{f3(t.mcc, 2)}</td><td className="num">{t.fn}</td><td className="num">{t.fp}</td></tr>)}</tbody></table></div>
        <p className="small muted" style={{ marginTop: 8 }}>Lowering the threshold catches more defects (fewer false negatives) but sends more clean code to review (more false positives). The right balance depends on the cost of a missed defect versus a wasted review.</p>
      </div>
    </>
  );
}

function CrossProject({ r }: { r: any }) {
  const algos = [...new Set(r.lopo.map((x: any) => x.algorithm))] as string[];
  const projects = [...new Set(r.lopo.map((x: any) => x.held_out))] as string[];
  const [algo, setAlgo] = useState(algos.find((a) => a !== "dummy") ?? algos[0]);
  const get = (a: string, p: string) => r.lopo.find((x: any) => x.algorithm === a && x.held_out === p);
  const pair = (a: string, t: string, te: string) => r.pairwise.find((x: any) => x.algorithm === algo && x.train === t && x.test === te);
  const heat = (v: number | null) => v === null || v === undefined ? "#fff" : `rgba(47,125,79,${Math.max(0, (v - 0.5) / 0.4)})`;
  return (
    <>
      <div className="panel">
        <h2>Leave-one-project-out ROC-AUC</h2>
        <p className="small muted" style={{ marginBottom: 8 }}>Each column: train on the other projects, test on the one named. {Object.entries(r.languages).map(([p, l]) => `${p}=${l === "cpp" ? "C++" : "C"}`).join(", ")}.</p>
        <table className="t"><thead><tr><th>Algorithm</th>{projects.map((p) => <th key={p} className="num">{p}</th>)}</tr></thead>
          <tbody>{algos.map((a) => <tr key={a}><td>{a}</td>{projects.map((p) => { const m = get(a, p)?.metrics; return <td key={p} className="num" style={{ background: heat(m?.roc_auc) }}>{f3(m?.roc_auc)}</td>; })}</tr>)}</tbody></table>
      </div>
      <div className="panel">
        <h2>Within-project vs cross-project</h2>
        <p className="small muted" style={{ marginBottom: 8 }}>The gap shows how much performance depends on having seen the same project during training.</p>
        <table className="t"><thead><tr><th>Algorithm</th><th>Project</th><th className="num">Within AUC</th><th className="num">Cross AUC</th><th className="num">Δ</th><th className="num">Within MCC</th><th className="num">Cross MCC</th></tr></thead>
          <tbody>{r.generalisation_gap.map((g: any) => <tr key={g.algorithm + g.project}><td>{g.algorithm}</td><td>{g.project}</td><td className="num">{f3(g.within_auc)}</td><td className="num">{f3(g.cross_auc)}</td><td className="num" style={{ color: g.cross_auc - g.within_auc < -0.03 ? "var(--sev-high)" : undefined }}>{(g.cross_auc - g.within_auc >= 0 ? "+" : "") + (g.cross_auc - g.within_auc).toFixed(3)}</td><td className="num">{f3(g.within_mcc, 2)}</td><td className="num">{f3(g.cross_mcc, 2)}</td></tr>)}</tbody></table>
      </div>
      <div className="grid cols-2">
        <div className="panel">
          <div className="panel-head"><h2>Train on one, test on another</h2>
            <select className="input" style={{ width: 130 }} value={algo} onChange={(e) => setAlgo(e.target.value)}>{algos.filter((a) => a !== "dummy").map((a) => <option key={a}>{a}</option>)}</select></div>
          <table className="t"><thead><tr><th>train ↓ / test →</th>{projects.map((p) => <th key={p} className="num">{p}</th>)}</tr></thead>
            <tbody>{projects.map((t) => <tr key={t}><td><b>{t}</b></td>{projects.map((te) => { const x = t === te ? null : pair(algo, t, te); return <td key={te} className="num" style={{ background: heat(x?.metrics.roc_auc) }} title={x?.cross_language ? "cross-language (C ↔ C++)" : ""}>{x ? f3(x.metrics.roc_auc, 2) + (x.cross_language ? " †" : "") : "·"}</td>; })}</tr>)}</tbody></table>
          <p className="small muted" style={{ marginTop: 6 }}>† C ↔ C++ transfer</p>
        </div>
        <div className="panel"><h2>Domain shift (mean KS statistic)</h2>
          <p className="small muted" style={{ marginBottom: 6 }}>0 = identical metric distributions, 1 = completely different.</p>
          <table className="t"><thead><tr><th>Pair</th><th className="num">Mean KS</th><th>Most shifted</th></tr></thead>
            <tbody>{Object.entries(r.domain_shift).sort((a: any, b: any) => b[1].mean_ks - a[1].mean_ks).slice(0, 8).map(([k, v]: any) => <tr key={k}><td>{k.replace("->", " → ")}</td><td className="num">{v.mean_ks.toFixed(2)}</td><td className="small mono">{v.top_shifted.slice(0, 2).map((t: any) => t.feature.replace("HALSTEAD_", "H_")).join(", ")}</td></tr>)}</tbody></table></div>
      </div>
    </>
  );
}

function Calibration({ r }: { r: any }) {
  const algos = [...new Set(r.results.map((x: any) => x.algorithm))] as string[];
  const [algo, setAlgo] = useState(algos[0]);
  const rows = r.results.filter((x: any) => x.algorithm === algo);
  const color: Record<string, string> = { none: "#8a95a0", sigmoid: "#2c4fcf", isotonic: "#a8223b" };
  return (
    <>
      <div className="row">{algos.map((a) => <button key={a} className={"btn" + (a === algo ? " primary" : "")} onClick={() => setAlgo(a)}>{a}</button>)}</div>
      <div className="grid cols-2">
        <div className="panel"><h2>Reliability on {r.project}</h2>
          <CurvePlot diagonal xLabel="Mean predicted probability" yLabel="Observed defect rate"
            series={rows.map((x: any) => ({ name: x.calibration, color: color[x.calibration], points: x.reliability.bins.map((b: any) => [b.mean_predicted, b.observed_rate] as [number, number]) }))} />
          <Legend items={rows.map((x: any) => ({ name: x.calibration === "none" ? "uncalibrated" : x.calibration, color: color[x.calibration] }))} />
          <p className="small muted" style={{ marginTop: 6 }}>On the dashed diagonal, “30% risk” means 30% of such modules were defective.</p></div>
        <div className="panel"><h2>Scores</h2>
          <table className="t"><thead><tr><th>Calibration</th><th className="num">Brier</th><th className="num">ECE</th><th className="num">ROC-AUC</th></tr></thead>
            <tbody>{rows.map((x: any) => <tr key={x.calibration}><td>{x.calibration}</td><td className="num">{f3(x.summary.brier.mean, 4)}</td><td className="num">{f3(x.ece, 4)}</td><td className="num">{f3(x.summary.roc_auc.mean)}</td></tr>)}</tbody></table>
          <p className="small muted" style={{ margin: "8px 0" }}>Brier score and ECE: lower is better. Calibration changes the probabilities but barely changes ranking (AUC).</p>
          <h3 style={{ marginBottom: 6 }}>Probability distribution (uncalibrated)</h3>
          <div className="hist" style={{ height: 70 }}>{rows[0].reliability.histogram.counts.map((c: number, i: number) => <div className="col" key={i}><i style={{ height: `${(c / Math.max(...rows[0].reliability.histogram.counts)) * 100}%`, background: "var(--static)" }} /></div>)}</div>
          <div className="row small muted" style={{ justifyContent: "space-between" }}><span>0</span><span>predicted probability</span><span>1</span></div></div>
      </div>
    </>
  );
}

function Ablation({ r }: { r: any }) {
  return (
    <div className="panel">
      <h2>Removing feature groups ({r.algorithm} on {r.project})</h2>
      <p className="small muted" style={{ marginBottom: 10 }}>ROC-AUC with the group removed or used alone. Bars show the mean; the dark tick is one standard deviation across folds.</p>
      <HBars rows={r.results.map((x: any) => ({ label: `${x.config} (${x.n_features})`, value: x.summary.roc_auc.mean, err: x.summary.roc_auc.std,
        color: x.config === "all features" ? "var(--ink)" : "var(--structural)" }))} max={1} />
      <table className="t" style={{ marginTop: 12 }}><thead><tr><th>Configuration</th><th className="num">Features</th><th className="num">ROC-AUC</th><th className="num">Δ vs all</th><th className="num">MCC</th></tr></thead>
        <tbody>{r.results.map((x: any) => <tr key={x.config}><td>{x.config}</td><td className="num">{x.n_features}</td><td className="num">{pm(x.summary.roc_auc)}</td><td className="num">{x.delta_auc_vs_all >= 0 ? "+" : ""}{x.delta_auc_vs_all.toFixed(3)}</td><td className="num">{pm(x.summary.mcc, 2)}</td></tr>)}</tbody></table>
      <div className="notice warn" style={{ marginTop: 10 }}><b>Not available with this data:</b> {Object.entries(r.unavailable_groups).map(([k, v]) => `${k} (${v})`).join(" ")}</div>
    </div>
  );
}

function ErrorAnalysis({ r }: { r: any }) {
  const cols = Object.keys(r.groups.TP.median ?? {});
  const label: Record<string, string> = { TP: "True positives (defects caught)", FP: "False positives (false alarms)", FN: "False negatives (defects missed)", TN: "True negatives (correctly cleared)" };
  const sig = r.contrasts.filter((c: any) => c.p < 0.05).sort((a: any, b: any) => Math.abs(b.smd) - Math.abs(a.smd)).slice(0, 8);
  return (
    <>
      {r.insights.length > 0 && <div className="panel"><h2>Systematic patterns</h2><ul style={{ paddingLeft: 18, margin: 0 }}>{r.insights.map((i: string) => <li key={i}>{i}</li>)}</ul></div>}
      <div className="panel"><h2>Outcome groups ({r.algorithm} on {r.project}, out-of-fold)</h2>
        <table className="t"><thead><tr><th>Group</th><th className="num">Count</th><th className="num">Mean prob.</th>{cols.map((c) => <th key={c} className="num">median {c.replace("CYCLOMATIC_COMPLEXITY", "CC").replace("HALSTEAD_", "H_")}</th>)}</tr></thead>
          <tbody>{["TP", "FN", "FP", "TN"].map((g) => <tr key={g}><td>{label[g]}</td><td className="num">{r.groups[g].count}</td><td className="num">{f3(r.groups[g].mean_probability, 2)}</td>{cols.map((c) => <td key={c} className="num">{r.groups[g].median[c]?.toFixed(1) ?? "–"}</td>)}</tr>)}</tbody></table></div>
      <div className="grid cols-2">
        <div className="panel"><h2>Errors by {r.error_by_size_quartile.feature}</h2>
          <table className="t"><thead><tr><th>Quartile</th><th className="num">n</th><th className="num">Defect rate</th><th className="num">Miss rate</th><th className="num">False-alarm rate</th></tr></thead>
            <tbody>{r.error_by_size_quartile.bins.map((b: any) => <tr key={b.bin}><td className="mono">{b.bin}</td><td className="num">{b.n}</td><td className="num">{(b.defect_rate * 100).toFixed(0)}%</td><td className="num">{b.miss_rate === null ? "–" : (b.miss_rate * 100).toFixed(0) + "%"}</td><td className="num">{b.false_alarm_rate === null ? "–" : (b.false_alarm_rate * 100).toFixed(0) + "%"}</td></tr>)}</tbody></table></div>
        <div className="panel"><h2>What distinguishes the errors</h2>
          <table className="t"><thead><tr><th>Contrast</th><th>Feature</th><th className="num">Median A</th><th className="num">Median B</th><th className="num">p</th></tr></thead>
            <tbody>{sig.length ? sig.map((c: any) => <tr key={c.contrast + c.feature}><td>{c.contrast}</td><td className="mono">{c.feature}</td><td className="num">{c.median_a.toFixed(1)}</td><td className="num">{c.median_b.toFixed(1)}</td><td className="num">{c.p < 0.001 ? "<0.001" : c.p.toFixed(3)}</td></tr>) : <tr><td colSpan={5} className="muted">No significant differences.</td></tr>}</tbody></table></div>
      </div>
      {[["hardest_false_negatives", "Defects the model was most confident were clean"], ["hardest_false_positives", "Clean modules the model was most confident were defective"]].map(([k, title]) => (
        <div className="panel" key={k}><h2>{title}</h2><div style={{ overflowX: "auto" }}><table className="t"><thead><tr><th className="num">Row</th><th className="num">Prob.</th>{cols.map((c) => <th key={c} className="num">{c.replace("CYCLOMATIC_COMPLEXITY", "CC").replace("HALSTEAD_", "H_")}</th>)}</tr></thead>
          <tbody>{r[k].slice(0, 6).map((c: any) => <tr key={c.row}><td className="num">{c.row}</td><td className="num">{c.probability.toFixed(2)}</td>{cols.map((x) => <td key={x} className="num">{c.values[x]?.toFixed(1)}</td>)}</tr>)}</tbody></table></div></div>
      ))}
    </>
  );
}
