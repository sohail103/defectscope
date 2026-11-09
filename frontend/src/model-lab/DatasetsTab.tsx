import { useCallback, useEffect, useState } from "react";
import { api, fmt, post } from "../api";
import type { DatasetProfile, DatasetStatus, FeatureDef, Scatter } from "../types/lab";
import { BinaryScatter, HBars } from "../visualizations/charts";

const VERSION_LABEL: Record<string, string> = {
  original: "Original (many duplicates)", cleaned_Dprime: "Cleaned D′ (Shepperd et al.)", cleaned_DDprime: "Cleaned D″ (deduplicated)",
};

export default function DatasetsTab() {
  const [status, setStatus] = useState<DatasetStatus | null>(null);
  const [schema, setSchema] = useState<{ features: FeatureDef[] } | null>(null);
  const [project, setProject] = useState("KC1");
  const [version, setVersion] = useState("cleaned_DDprime");
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [feature, setFeature] = useState("CYCLOMATIC_COMPLEXITY");
  const [scatter, setScatter] = useState<Scatter | null>(null);
  const [sort, setSort] = useState<"effect" | "name">("effect");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => api<DatasetStatus[]>("/datasets").then((d) => setStatus(d[0])), []);
  useEffect(() => { load(); api<{ features: FeatureDef[] }>("/feature-schema").then(setSchema); }, [load]);
  useEffect(() => {
    if (!status?.present) return;
    setProfile(null); setError(null);
    api<DatasetProfile>(`/datasets/nasa_mdp/profile?project=${project}&version=${version}`).then(setProfile).catch((e) => setError(e.message));
  }, [status?.present, project, version]);
  useEffect(() => {
    if (!status?.present) return;
    api<Scatter>(`/datasets/nasa_mdp/scatter?project=${project}&version=${version}&feature=${feature}`).then(setScatter).catch(() => setScatter(null));
  }, [status?.present, project, version, feature]);

  const download = async () => {
    setBusy(true); setError(null);
    try { await post("/datasets/nasa_mdp/fetch"); await load(); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const upload = async (f: File) => {
    setBusy(true); setError(null);
    const fd = new FormData(); fd.append("file", f);
    try { const r = await fetch("/api/datasets/nasa_mdp/import", { method: "POST", body: fd }); if (!r.ok) throw new Error((await r.json()).detail); await load(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  if (!status) return <div className="page muted">Loading…</div>;
  if (!status.present) {
    return (
      <div className="page grid">
        <div className="panel">
          <h2>NASA MDP defect datasets</h2>
          <p className="muted" style={{ margin: "6px 0 12px", maxWidth: 720 }}>{status.description} The data is downloaded once from a public GitHub mirror
            ({status.source.replace("https://", "").split("/").slice(0, 3).join("/")}) and stored locally with a checksum. Nothing about your projects is sent anywhere.</p>
          {error && <div className="notice error" style={{ marginBottom: 10 }}>{error}</div>}
          <div className="row">
            <button className="btn primary" disabled={busy} onClick={download}>{busy ? "Downloading…" : "Download datasets"}</button>
            <label className="btn" style={{ cursor: "pointer" }}>Import ZIP manually<input type="file" accept=".zip" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>
          </div>
        </div>
      </div>
    );
  }

  const feats = profile ? [...profile.features].sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : Math.abs((b.auc_effect ?? 0.5) - 0.5) - Math.abs((a.auc_effect ?? 0.5) - 0.5)) : [];
  const defByName = Object.fromEntries((schema?.features ?? []).map((f) => [f.name, f]));
  const commonOnly = (n: string) => status.common_features.includes(n);

  return (
    <div className="page grid">
      <div className="panel">
        <div className="panel-head"><h2>NASA MDP</h2>
          <span className="small muted">retrieved {status.provenance?.retrieved_at} · archive sha256 {status.provenance?.archive_sha256.slice(0, 12)}…</span></div>
        <div className="row">
          <label className="field">Project
            <select className="input" value={project} onChange={(e) => setProject(e.target.value)}>
              {Object.entries(status.projects).map(([k, v]) => <option key={k} value={k}>{k} · {v.language === "cpp" ? "C++" : "C"} · {v.domain}</option>)}
            </select></label>
          <label className="field">Version
            <select className="input" value={version} onChange={(e) => setVersion(e.target.value)}>
              {status.versions.map((v) => <option key={v} value={v}>{VERSION_LABEL[v] ?? v}</option>)}
            </select></label>
        </div>
      </div>
      {error && <div className="notice error">{error}</div>}
      {!profile ? <div className="muted">Profiling…</div> : (
        <>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
            <div className="stat"><b>{fmt(profile.rows)}</b><span>modules (functions)</span></div>
            <div className="stat"><b>{profile.n_features}</b><span>features</span></div>
            <div className="stat"><b>{(profile.defect_rate * 100).toFixed(1)}%</b><span>defective ({fmt(profile.defective)}) · {profile.imbalance_ratio}:1 imbalance</span></div>
            <div className="stat"><b>{(profile.duplicate_fraction * 100).toFixed(0)}%</b><span>rows with a feature-identical twin</span></div>
            <div className="stat"><b>{profile.missing_cells}</b><span>missing cells</span></div>
          </div>
          {profile.duplicate_fraction > 0.05 && <div className="notice warn"><b>Duplicates inflate scores.</b> {profile.duplicate_feature_rows} rows duplicate another row's features
            ({profile.conflicting_duplicate_rows} have contradictory labels). With random train/test splits, a row's twin can land in the test set, so results on this version look better than they are. Use the deduplicated D″ version for experiments.</div>}
          {profile.branch_count_equals_2cc_minus_1 !== null && <div className="notice">BRANCH_COUNT equals 2·CYCLOMATIC_COMPLEXITY − 1 in {(profile.branch_count_equals_2cc_minus_1 * 100).toFixed(1)}% of rows, so it carries almost no information beyond cyclomatic complexity.</div>}

          <div className="grid cols-2">
            <div className="panel">
              <div className="panel-head"><h2>Defect rate by {feature.toLowerCase().replace(/_/g, " ")}</h2>
                <select className="input" style={{ width: 230 }} value={feature} onChange={(e) => setFeature(e.target.value)}>
                  {status.common_features.map((f) => <option key={f}>{f}</option>)}</select></div>
              {scatter && <>
                <HBars rows={scatter.bins.map((b) => ({ label: <span className="mono">{b.range}</span>, value: b.defect_rate, color: "var(--risk)", note: b.n }))}
                  max={Math.max(0.05, ...scatter.bins.map((b) => b.defect_rate))} fmt={(v) => (v * 100).toFixed(0) + "%"} />
                <p className="small muted" style={{ margin: "8px 0 6px" }}>Each bar is a quantile bin of the feature. Spearman ρ = {scatter.spearman?.toFixed(2) ?? "–"}{scatter.p !== null && scatter.p !== undefined ? ` (p=${scatter.p.toExponential(1)})` : ""}. {scatter.note}</p>
                <BinaryScatter points={scatter.points} xLabel={feature} />
              </>}
            </div>
            <div className="panel">
              <h2>Which metrics separate defective modules?</h2>
              <p className="small muted" style={{ marginBottom: 8 }}>Probability that a random defective module has a higher value than a random clean one (0.5 = no separation).
                Mann-Whitney p-values are Benjamini–Hochberg adjusted across features.</p>
              <HBars rows={[...profile.features].filter((f) => f.auc_effect !== null).sort((a, b) => b.auc_effect! - a.auc_effect!).slice(0, 12)
                .map((f) => ({ label: f.name, value: f.auc_effect! - 0.5, color: "var(--structural)" }))} signed max={0.5} fmt={(v) => (v + 0.5).toFixed(2)} />
              {profile.high_correlation_pairs.length > 0 && <details style={{ marginTop: 10 }}><summary className="small">{profile.high_correlation_pairs.length} highly correlated feature pairs (|ρ| ≥ 0.9)</summary>
                <ul className="small" style={{ paddingLeft: 18 }}>{profile.high_correlation_pairs.slice(0, 12).map((p) => <li key={p.a + p.b}><span className="mono">{p.a}</span> ~ <span className="mono">{p.b}</span> ({p.spearman})</li>)}</ul></details>}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><h2>Features</h2>
              <span className="small muted">sort by <button className="btn small" onClick={() => setSort(sort === "effect" ? "name" : "effect")}>{sort === "effect" ? "separation" : "name"}</button></span></div>
            <div style={{ overflowX: "auto" }}>
              <table className="t"><thead><tr><th>Feature</th><th>Group</th><th className="num">Median (clean)</th><th className="num">Median (defective)</th><th className="num">Max</th><th className="num">Skew</th>
                <th className="num">IQR outliers</th><th className="num">ρ</th><th className="num">Separation</th><th className="num">p (BH)</th><th>On uploaded code</th></tr></thead>
                <tbody>{feats.map((f) => {
                  const d = defByName[f.name];
                  return (
                    <tr key={f.name} title={d?.description}>
                      <td className="mono">{f.name}{!commonOnly(f.name) && <span className="badge" style={{ marginLeft: 6 }}>{project}-only</span>}</td>
                      <td>{d?.group ?? "–"}</td><td className="num">{fmt(f.median_clean, 2)}</td><td className="num">{fmt(f.median_defective, 2)}</td>
                      <td className="num">{fmt(f.max, 1)}</td><td className="num">{f.skew.toFixed(1)}</td><td className="num">{f.iqr_outliers}</td>
                      <td className="num">{f.spearman_with_defect?.toFixed(2) ?? "–"}</td><td className="num">{f.auc_effect?.toFixed(2) ?? "–"}</td>
                      <td className="num">{f.p_adjusted_bh === null ? "–" : f.p_adjusted_bh < 0.001 ? "<0.001" : f.p_adjusted_bh.toFixed(3)}</td>
                      <td title={d?.caveat}>{d ? <span className={"badge" + (d.extraction === "unavailable" ? " sev-high" : d.extraction === "derived" ? "" : " sev-warning")}>{d.extraction}</span> : "–"}</td>
                    </tr>);
                })}</tbody></table>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>Outliers are reported, never removed automatically. “On uploaded code” says whether DefectScope can re-measure the feature from source:
              approximate = similar but not identical to the NASA tool; derived = formula of approximate counts; unavailable = cannot be measured, so models using it never run on uploaded projects.</p>
          </div>

          <div className="grid cols-2">
            <div className="panel"><h2>Known limitations</h2><ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{profile.limitations.map((l) => <li key={l}>{l}</li>)}</ul></div>
            <div className="panel"><h2>Provenance</h2>
              <dl className="kv small"><dt>File</dt><dd>{profile.provenance.file}</dd><dt>File sha256</dt><dd>{String(profile.provenance.sha256).slice(0, 16)}…</dd>
                <dt>Source</dt><dd>klainfo/NASADefectDataset</dd><dt>Application domain</dt><dd>{profile.provenance.domain}</dd><dt>Language</dt><dd>{profile.language === "cpp" ? "C++" : "C"}</dd>
                <dt>Granularity</dt><dd>{profile.granularity}</dd></dl>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
