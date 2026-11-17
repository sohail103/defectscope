import { useEffect, useState } from "react";
import { api, bytes } from "../api";
import type { ToolInfo } from "../types";
import type { ProjectCtx } from "../pages/ProjectPage";

interface PassInfo { name: string; description: string; requires: string[]; produces: string[]; languages: string[] | null; granularity: string[] }

export default function SetupTab({ ctx }: { ctx: ProjectCtx }) {
  const { config, setConfig, detail, job, overview } = ctx;
  const [passes, setPasses] = useState<PassInfo[]>([]);
  const [tools, setTools] = useState<{ static_analysis: ToolInfo[]; git: { available: boolean } } | null>(null);
  useEffect(() => { api<PassInfo[]>("/passes").then(setPasses); api<typeof tools>("/tools").then(setTools); }, []);
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

      <div className="grid cols-2">
        <div className="panel">
          <div className="panel-head"><h2>Static-analysis tools</h2>
            <label className="toggle"><input type="checkbox" checked={config.static_analysis.enabled} onChange={(e) => setConfig({ ...config, static_analysis: { ...config.static_analysis, enabled: e.target.checked } })} />enabled</label></div>
          <p className="small muted" style={{ marginBottom: 8 }}>External tools inspect the code without running it. Project-supplied tool settings are ignored; DefectScope passes its own.</p>
          <div className="grid" style={{ gap: 8 }}>
            {(tools?.static_analysis ?? []).map((t) => {
              const on = config.static_analysis.tools.includes(t.name);
              return (
                <div key={t.name} style={{ opacity: t.available ? 1 : 0.7 }}>
                  <label className="toggle"><input type="checkbox" disabled={!t.available || !config.static_analysis.enabled} checked={on && t.available}
                    onChange={(e) => setConfig({ ...config, static_analysis: { ...config.static_analysis, tools: e.target.checked ? [...config.static_analysis.tools, t.name] : config.static_analysis.tools.filter((x) => x !== t.name) } })} />
                    <b style={{ fontWeight: 500 }}>{t.name}</b> <span className="faint small">{t.languages.map((l) => (l === "cpp" ? "C++" : l)).join(", ")}{t.available && t.version ? ` · ${t.version.replace(/^.*?(\d)/, "$1")}` : ""}</span></label>
                  <div className="small muted" style={{ marginLeft: 22 }}>{t.description}{!t.available && <> <span style={{ color: "var(--sev-high)" }}>Not installed:</span> <code>{t.install_hint}</code></>}{!t.default_enabled && t.available && " (off by default: slower or needs setup)"}</div>
                </div>);
            })}
          </div>
          <label className="field" style={{ marginTop: 10, width: 160 }}>Timeout per tool (s)
            <input className="input" type="number" min={10} value={config.static_analysis.timeout_s} onChange={(e) => setConfig({ ...config, static_analysis: { ...config.static_analysis, timeout_s: +e.target.value } })} /></label>
        </div>
        <div className="grid" style={{ alignContent: "start" }}>
          <div className="panel">
            <div className="panel-head"><h2>Git history</h2>
              <label className="toggle"><input type="checkbox" checked={config.history.enabled} onChange={(e) => setConfig({ ...config, history: { ...config.history, enabled: e.target.checked } })} />enabled</label></div>
            <p className="small muted" style={{ marginBottom: 8 }}>{s.has_git ? "A .git folder was found." : "No .git folder in this project, so history will be skipped."} {tools && !tools.git.available && <b style={{ color: "var(--sev-high)" }}>The git program is not installed.</b>}</p>
            <div className="row">
              <label className="field">Use commits up to (optional)
                <input className="input" type="date" value={config.history.until ?? ""} onChange={(e) => setConfig({ ...config, history: { ...config.history, until: e.target.value || null } })} /></label>
              <label className="field" style={{ width: 120 }}>Max commits
                <input className="input" type="number" min={50} value={config.history.max_commits} onChange={(e) => setConfig({ ...config, history: { ...config.history, max_commits: +e.target.value } })} /></label>
            </div>
            <p className="small muted" style={{ marginTop: 6 }}>A cutoff date uses only commits up to that day, so values match what was knowable at that point (no temporal leakage).</p>
          </div>
          <div className="panel">
            <div className="panel-head"><h2>Duplicate code</h2>
              <label className="toggle"><input type="checkbox" checked={config.clones.enabled} onChange={(e) => setConfig({ ...config, clones: { ...config.clones, enabled: e.target.checked } })} />enabled</label></div>
            <div className="row">
              <label className="field" style={{ width: 150 }}>Min function SLOC<input className="input" type="number" min={3} value={config.clones.min_function_sloc} onChange={(e) => setConfig({ ...config, clones: { ...config.clones, min_function_sloc: +e.target.value } })} /></label>
              <label className="field" style={{ width: 150 }}>Min syntax nodes<input className="input" type="number" min={10} value={config.clones.min_nodes} onChange={(e) => setConfig({ ...config, clones: { ...config.clones, min_nodes: +e.target.value } })} /></label>
            </div>
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
