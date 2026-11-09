import { useEffect, useState } from "react";
import { api, bytes } from "../api";
import type { ProjectCtx } from "../pages/ProjectPage";

interface PassInfo { name: string; description: string; requires: string[]; produces: string[]; languages: string[] | null; granularity: string[] }

export default function SetupTab({ ctx }: { ctx: ProjectCtx }) {
  const { config, setConfig, detail, job, overview } = ctx;
  const [passes, setPasses] = useState<PassInfo[]>([]);
  useEffect(() => { api<PassInfo[]>("/passes").then(setPasses); }, []);
  if (!config) return <div className="page muted">Loading…</div>;
  const ex = config.exclusions;
  const set = (patch: Partial<typeof ex>) => setConfig({ ...config, exclusions: { ...ex, ...patch } });
  const s = detail.meta.summary;
  const results = job?.passes?.length ? job.passes : overview?.passes ?? [];
  const status = Object.fromEntries(results.map((r) => [r.name, r]));

  return (
    <div className="page grid">
      <div className="grid cols-2">
        <div className="panel">
          <h2>What was found</h2>
          <dl className="kv small">
            <dt>Supported source files</dt><dd>{s.analysable_files}</dd>
            <dt>Excluded files</dt><dd>{s.excluded_files}</dd>
            <dt>Excluded directories</dt><dd>{Object.keys(s.excluded_directories).length}</dd>
            <dt>Git history present</dt><dd>{s.has_git ? "yes" : "no"}</dd>
            <dt>compile_commands.json</dt><dd>{s.has_compile_commands ? "found" : "not found"}</dd>
            <dt>Total size</dt><dd>{bytes(detail.meta.total_bytes)}</dd>
          </dl>
          {Object.keys(s.build_systems).length > 0 && <p className="small muted" style={{ marginTop: 10 }}>Build systems: {Object.keys(s.build_systems).join(", ")}</p>}
          {s.header_language_assumption && <p className="small muted" style={{ marginTop: 6 }}>`.h` headers are parsed as {s.header_language_assumption} because of the other sources in this project.</p>}
          {Object.keys(s.excluded_directories).length > 0 && (
            <details style={{ marginTop: 10 }}><summary className="small">Excluded directories</summary>
              <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {Object.entries(s.excluded_directories).slice(0, 30).map(([d, why]) => <li key={d}><code>{d}</code> <span className="muted">({why})</span></li>)}
              </ul>
            </details>
          )}
        </div>

        <div className="panel">
          <h2>Exclusions</h2>
          <div className="grid" style={{ gap: 8 }}>
            <label className="toggle"><input type="checkbox" checked={ex.exclude_vendored} onChange={(e) => set({ exclude_vendored: e.target.checked })} /> Skip vendored dependencies (vendor, third_party, extern…)</label>
            <label className="toggle"><input type="checkbox" checked={ex.exclude_generated} onChange={(e) => set({ exclude_generated: e.target.checked })} /> Skip generated code (marker comments, protobuf output)</label>
            <label className="toggle"><input type="checkbox" checked={ex.exclude_tests} onChange={(e) => set({ exclude_tests: e.target.checked })} /> Skip test files</label>
            <label className="field">Extra exclusion patterns (one per line, glob)
              <textarea className="input" style={{ minHeight: 70 }} value={ex.extra_globs.join("\n")} onChange={(e) => set({ extra_globs: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />
            </label>
            <label className="field">Skip files larger than (KB)
              <input className="input" type="number" min={16} value={Math.round(ex.max_file_bytes / 1024)} onChange={(e) => set({ max_file_bytes: Math.max(16, +e.target.value) * 1024 })} />
            </label>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><h2>Structural thresholds</h2><span className="small muted">Flag complexity indicators. These are not defect predictions.</span></div>
        <div className="grid cols-4">
          {Object.entries(config.thresholds).map(([k, v]) => (
            <label className="field" key={k}>{k.replace(/_/g, " ")}
              <input className="input" type="number" min={1} value={v} onChange={(e) => setConfig({ ...config, thresholds: { ...config.thresholds, [k]: +e.target.value } })} />
            </label>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><h2>Analysis passes</h2><span className="small muted">Each pass declares its inputs; dependencies are resolved automatically.</span></div>
        <div className="passlist">
          {passes.map((p) => {
            const r = status[p.name];
            return (
              <div className="passrow" key={p.name} title={p.description}>
                <span className={"dot " + (r?.status ?? "")} />
                <span><b style={{ fontWeight: 500 }}>{p.name.replace(/_/g, " ")}</b></span>
                <span className="muted">{r?.message || p.description}</span>
                <span className="muted num" style={{ textAlign: "right" }}>{r?.duration_s ? r.duration_s.toFixed(2) + "s" : ""}</span>
              </div>
            );
          })}
        </div>
        {results.some((r) => r.warnings.length > 0) && (
          <details style={{ marginTop: 10 }}><summary className="small">Warnings ({results.reduce((n, r) => n + r.warnings.length, 0)})</summary>
            <ul className="small" style={{ paddingLeft: 18 }}>
              {results.flatMap((r) => r.warnings.map((w, i) => <li key={r.name + i}><b>{r.name}:</b> <span className="muted">{w.slice(0, 220)}</span></li>))}
            </ul>
          </details>
        )}
        <div style={{ marginTop: 14 }} className="row">
          <button className="btn primary" disabled={ctx.running} onClick={ctx.run}>{overview ? "Re-run analysis" : "Run analysis"}</button>
          {overview && <span className="small muted">Last run {new Date(overview.created_at).toLocaleString()} (v{overview.analysis_version})</span>}
        </div>
      </div>
    </div>
  );
}
