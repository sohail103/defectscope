import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Graph } from "../types";
import { forceLayout } from "../visualizations/layout";
import type { ProjectCtx } from "../pages/ProjectPage";

const LANG_COLOR: Record<string, string> = { python: "#3d7ab8", c: "#6b7280", cpp: "#8f5fb0" };

export default function GraphTab({ ctx }: { ctx: ProjectCtx }) {
  const [g, setG] = useState<Graph | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const aid = ctx.overview?.analysis_id;
  useEffect(() => { if (aid) api<Graph>(`/projects/${ctx.id}/graph`).then(setG); }, [ctx.id, aid]);
  const W = 1000, H = 560;
  const pos = useMemo(() => (g && g.nodes.length <= 400 ? forceLayout(g.nodes, g.edges, W, H) : null), [g]);

  if (!ctx.overview) return <div className="page"><div className="panel empty"><h2>No analysis yet</h2><p>Run the analysis to build the dependency graph.</p></div></div>;
  if (!g) return <div className="page muted">Loading…</div>;
  const connected = hover ? new Set([hover, ...g.edges.filter((e) => e.source === hover).map((e) => e.target), ...g.edges.filter((e) => e.target === hover).map((e) => e.source)]) : null;
  const byFanIn = [...g.nodes].sort((a, b) => b.fan_in - a.fan_in).slice(0, 8);
  const byFanOut = [...g.nodes].sort((a, b) => b.fan_out - a.fan_out).slice(0, 8);

  return (
    <div className="page grid">
      <div className="notice">{g.note}</div>
      {g.cycles.length > 0 && (
        <div className="notice warn"><b>{g.cycles.length} dependency cycle group{g.cycles.length > 1 ? "s" : ""}:</b>{" "}
          {g.cycles.slice(0, 3).map((c) => c.join(" ↔ ")).join(" · ")}</div>
      )}
      {!pos ? <div className="notice warn">Graph has {g.nodes.length} files; the interactive layout is limited to 400. Use the tables below.</div> : (
        <svg className="graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="File dependency graph">
          <defs><marker id="arr" viewBox="0 0 8 8" refX="14" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#9aa5ad" /></marker></defs>
          {g.edges.map((e, i) => {
            const a = pos[e.source], b = pos[e.target]; if (!a || !b) return null;
            const dim = connected && !(connected.has(e.source) && connected.has(e.target));
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={dim ? "#dde2de" : "#9aa5ad"} strokeWidth={1.2} markerEnd="url(#arr)" />;
          })}
          {g.nodes.map((n) => {
            const p = pos[n.id]; const r = 6 + Math.min(14, n.fan_in * 2);
            const dim = connected && !connected.has(n.id);
            return (
              <g key={n.id} className="gn" transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.25 : 1}
                onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} onClick={() => ctx.open(n.id)}>
                <title>{`${n.id}\nfan-in ${n.fan_in}, fan-out ${n.fan_out}${n.in_cycle ? "\nin a dependency cycle" : ""}`}</title>
                <circle r={r} fill={LANG_COLOR[n.language]} stroke={n.in_cycle ? "#a63d17" : "#fff"} strokeWidth={n.in_cycle ? 3 : 1.5} />
                {(hover === n.id || n.fan_in >= 2 || g.nodes.length < 25) && <text x={r + 4} y={4}>{n.id.split("/").pop()}</text>}
              </g>
            );
          })}
        </svg>
      )}
      <div className="row small muted"><span>Node size = fan-in · colour = language · rust ring = in a cycle · click to open</span></div>
      <div className="grid cols-2">
        <div className="panel"><h2>Most depended on (fan-in)</h2>
          <table className="t"><tbody>{byFanIn.map((n) => <tr key={n.id} className="click" onClick={() => ctx.open(n.id)}><td className="mono">{n.id}</td><td className="num">{n.fan_in}</td></tr>)}</tbody></table></div>
        <div className="panel"><h2>Depends on most (fan-out)</h2>
          <table className="t"><tbody>{byFanOut.map((n) => <tr key={n.id} className="click" onClick={() => ctx.open(n.id)}><td className="mono">{n.id}</td><td className="num">{n.fan_out}</td></tr>)}</tbody></table></div>
      </div>
      {Object.keys(g.external).length > 0 && (
        <div className="panel"><h2>External dependencies</h2>
          <p className="small muted">{Object.entries(g.external).slice(0, 30).map(([k, v]) => `${k} (${v})`).join(" · ")}</p></div>
      )}
    </div>
  );
}
