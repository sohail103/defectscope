import { useEffect, useState } from "react";
import { api } from "../api";
import { go } from "../App";
import CodeViewer, { Layers } from "../code-viewer/CodeViewer";
import FileTree from "../project-explorer/FileTree";
import Inspector from "../project-explorer/Inspector";
import type { Entity, Hotspot, TreeNode } from "../types";
import type { Prediction, PredictionDoc } from "../types/lab";
import type { ProjectCtx } from "../pages/ProjectPage";

export default function ExplorerTab({ ctx, params }: { ctx: ProjectCtx; params: URLSearchParams }) {
  const { id, overview } = ctx;
  const file = params.get("file") ?? undefined;
  const line = params.get("line") ? Number(params.get("line")) : undefined;
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [content, setContent] = useState<string>("");
  const [ents, setEnts] = useState<Entity[]>([]);
  const [hot, setHot] = useState<Hotspot[]>([]);
  const [sel, setSel] = useState<Entity | null>(null);
  const [layers, setLayers] = useState<Layers>({ heat: true, structural: true, staticAnalysis: false, risk: false });
  const [err, setErr] = useState<string | null>(null);
  const [pred, setPred] = useState<PredictionDoc | null>(null);
  const aid = overview?.analysis_id;

  useEffect(() => {
    const mid = sessionStorage.getItem(`model:${id}`);
    setPred(null);
    if (aid && mid) api<PredictionDoc | null>(`/projects/${id}/predictions?model_id=${mid}`).then((d) => { setPred(d); if (d) setLayers((l) => ({ ...l, risk: true })); }).catch(() => setPred(null));
  }, [id, aid]);
  useEffect(() => { api<TreeNode>(`/projects/${id}/tree`).then(setTree).catch((e) => setErr(e.message)); }, [id, aid]);
  useEffect(() => {
    setSel(null); setEnts([]); setHot([]);
    if (!file) { setContent(""); return; }
    const q = encodeURIComponent(file);
    api<{ content: string }>(`/projects/${id}/file?path=${q}`).then((r) => setContent(r.content)).catch((e) => setErr(e.message));
    if (aid) {
      api<Entity[]>(`/projects/${id}/entities?path=${q}&limit=5000`).then(setEnts);
      api<Hotspot[]>(`/projects/${id}/hotspots?path=${q}`).then(setHot);
    }
  }, [id, file, aid]);
  // jump to the entity that starts at the requested line (from overview links)
  useEffect(() => {
    if (line && ents.length) {
      const hit = ents.find((e) => e.kind !== "file" && e.range.start_line === line);
      if (hit) setSel(hit);
    }
  }, [line, ents]);

  const fileEnt = ents.find((e) => e.kind === "file");
  const language = fileEnt?.language ?? (tree && file ? findLang(tree, file) : null);
  const toggle = (k: keyof Layers) => setLayers((l) => ({ ...l, [k]: !l[k] }));

  return (
    <div className="explorer">
      <div className="pane left">
        {tree ? <FileTree root={tree} selected={file} onSelect={(p) => go(`/p/${id}/explorer?file=${encodeURIComponent(p)}`)} /> : <div className="muted small" style={{ padding: 12 }}>{err ?? "Loading…"}</div>}
      </div>
      <div className="codepane">
        {!file ? (
          <div className="empty"><h2>Pick a file</h2><p>Choose a source file on the left, or follow a link from the overview.</p>
            {!overview && <p style={{ marginTop: 8 }}>Run the analysis to see metrics and highlights.</p>}</div>
        ) : (
          <>
            <div className="codebar">
              <span className="path">{file}</span>
              <label className="toggle"><input type="checkbox" checked={layers.heat} onChange={() => toggle("heat")} />Complexity heat</label>
              <label className="toggle"><input type="checkbox" checked={layers.structural} onChange={() => toggle("structural")} />Structural flags</label>
              <label className="toggle off" title="No static-analysis tool has been run yet (planned: cppcheck, clang-tidy, Ruff, Pylint)"><input type="checkbox" disabled />Static analysis</label>
              {pred ? <label className="toggle"><input type="checkbox" checked={layers.risk} onChange={() => toggle("risk")} />Predicted risk</label>
                : <label className="toggle off" title="Open the Defect risk tab and apply a compatible model"><input type="checkbox" disabled />Predicted risk</label>}
            </div>
            <div className="codebar" style={{ borderBottom: "1px solid var(--rule-soft)", paddingTop: 5, paddingBottom: 5 }}>
              <div className="legend">
                <span><i className="key heat-key" />Complexity heat (darker = higher cyclomatic)</span>
                <span><i className="key bar-key" />Structural flag (left bar: yellow info, orange warning, rust high)</span>
                <span style={{ opacity: .5 }}><i className="key diag-key" />Static-analysis finding</span>
                <span style={{ opacity: pred ? 1 : .5 }}><i className="key risk-key" />Predicted risk (whole function, right lane)</span>
              </div>
            </div>
            <CodeViewer content={content} language={language} entities={ents} hotspots={hot} layers={layers} selected={sel} targetLine={line} onSelect={setSel}
              predictions={(pred?.predictions ?? []).filter((p: Prediction) => p.path === file)} modelName={pred?.model.name} />
          </>
        )}
      </div>
      <div className="pane right">
        {file ? <Inspector file={fileEnt} entities={ents} hotspots={hot} selected={sel} onSelect={setSel} />
          : <p className="muted small">Select a file to inspect its functions and classes.</p>}
      </div>
    </div>
  );
}

function findLang(n: TreeNode, path: string): string | null {
  if (n.type === "file") return n.path === path ? n.language ?? null : null;
  for (const c of n.children ?? []) { const r = findLang(c, path); if (r) return r; }
  return null;
}
