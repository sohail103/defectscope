import { useCallback, useEffect, useRef, useState } from "react";
import { api, bytes, post } from "../api";
import { go } from "../App";
import type { ProjectMeta } from "../types";

const SKIP = /(^|\/)(node_modules|\.venv|venv|__pycache__|site-packages)\//;

export default function ImportPage() {
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [snippet, setSnippet] = useState({ filename: "example.py", content: "def f(x):\n    if x > 0:\n        return 1\n    return 0\n" });
  const zipRef = useRef<HTMLInputElement>(null);
  const dirRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => api<ProjectMeta[]>("/projects").then(setProjects).catch((e) => setError(e.message)), []);
  useEffect(() => { refresh(); }, [refresh]);

  async function run(label: string, fn: () => Promise<ProjectMeta>) {
    setBusy(label); setError(null);
    try { const m = await fn(); go(`/p/${m.id}/overview`); } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  }
  const uploadZip = (file: File) => run("Extracting archive…", async () => {
    const fd = new FormData(); fd.append("file", file, file.name);
    const r = await fetch("/api/projects/upload-zip", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  });
  const uploadDir = (files: File[]) => run(`Uploading ${files.length} files…`, async () => {
    const fd = new FormData();
    const kept = files.filter((f) => !SKIP.test((f as any).webkitRelativePath || f.name));
    kept.forEach((f) => { fd.append("files", f, f.name); fd.append("paths", (f as any).webkitRelativePath || f.name); });
    fd.append("name", ((kept[0] as any)?.webkitRelativePath || "project").split("/")[0]);
    const r = await fetch("/api/projects/upload-dir", { method: "POST", body: fd });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  });

  return (
    <div className="page">
      <div style={{ maxWidth: 760, marginBottom: 24 }}>
        <h1>Find where a codebase gets complicated.</h1>
        <p className="muted" style={{ marginTop: 8 }}>
          Import a C, C++ or Python project to measure its structure, see where complexity concentrates, and (where a
          validated model applies) estimate module-level defect risk. Code is parsed, never executed, and stays on this machine.
        </p>
      </div>
      {error && <div className="notice error" style={{ marginBottom: 16 }}>{error}</div>}

      <div className="grid cols-2">
        <div
          className={"dropzone" + (over ? " over" : "")}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) uploadZip(f); }}
        >
          <h2>Import a project</h2>
          <p className="muted small" style={{ margin: "6px 0 14px" }}>Drop a ZIP here, or choose a ZIP or a folder. Folder structure is preserved.</p>
          <div className="row" style={{ justifyContent: "center" }}>
            <button className="btn primary" disabled={!!busy} onClick={() => zipRef.current?.click()}>Choose ZIP</button>
            <button className="btn" disabled={!!busy} onClick={() => dirRef.current?.click()}>Choose folder</button>
            <button className="btn" disabled={!!busy} onClick={() => run("Importing sample…", () => post<ProjectMeta>("/projects/sample"))}>Try the sample project</button>
          </div>
          <input ref={zipRef} type="file" accept=".zip" hidden onChange={(e) => e.target.files?.[0] && uploadZip(e.target.files[0])} />
          <input ref={dirRef} type="file" hidden
            // @ts-expect-error non-standard but widely supported directory picker
            webkitdirectory="" directory=""
            onChange={(e) => e.target.files && uploadDir(Array.from(e.target.files))} />
          {busy && <p className="small" style={{ marginTop: 14 }}>{busy}</p>}
        </div>

        <div className="panel">
          <h2>Analyse a single file</h2>
          <p className="muted small" style={{ marginBottom: 8 }}>Quick look at one file. Project import gives much richer results.</p>
          <label className="field" style={{ marginBottom: 8 }}>File name (extension picks the language)
            <input className="input" value={snippet.filename} onChange={(e) => setSnippet({ ...snippet, filename: e.target.value })} />
          </label>
          <textarea className="input" value={snippet.content} onChange={(e) => setSnippet({ ...snippet, content: e.target.value })} spellCheck={false} />
          <div style={{ marginTop: 10 }}>
            <button className="btn" disabled={!!busy || !snippet.content.trim()} onClick={() => run("Importing…", () => post<ProjectMeta>("/projects/snippet", snippet))}>Open file</button>
          </div>
        </div>
      </div>

      <h2 style={{ margin: "32px 0 10px" }}>Imported projects</h2>
      {projects.length === 0 ? (
        <div className="panel empty"><h2>Nothing imported yet</h2><p>Import a project above to begin.</p></div>
      ) : (
        <div className="projects-list">
          {projects.map((p) => (
            <div className="proj" key={p.id}>
              <button className="name" onClick={() => go(`/p/${p.id}/overview`)}>{p.name}</button>
              <span className="small muted">
                {Object.entries(p.summary.languages ?? {}).map(([l, v]) => `${v.files} ${l}`).join(", ") || "no supported source"} · {bytes(p.total_bytes)}
              </span>
              <button className="btn small danger" onClick={async () => {
                if (!confirm(`Delete "${p.name}" and its analyses from this machine?`)) return;
                await api(`/projects/${p.id}`, { method: "DELETE" }); refresh();
              }}>Delete</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
