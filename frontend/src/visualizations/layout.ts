export interface LNode { id: string }
export interface LEdge { source: string; target: string }
export interface P { x: number; y: number }

/** Small force-directed layout (Fruchterman–Reingold style with centring gravity). Deterministic. */
export function forceLayout(nodes: LNode[], edges: LEdge[], W: number, H: number, iterations = 300): Record<string, P> {
  const n = Math.max(1, nodes.length);
  const k = Math.min(80, Math.sqrt((W * H) / n) * 0.45); // ideal edge length
  const pos: Record<string, { x: number; y: number; dx: number; dy: number }> = {};
  nodes.forEach((nd, i) => {
    const a = (i / n) * Math.PI * 2;
    pos[nd.id] = { x: W / 2 + Math.cos(a) * Math.min(W, H) * 0.25, y: H / 2 + Math.sin(a) * Math.min(W, H) * 0.25, dx: 0, dy: 0 };
  });
  const ids = nodes.map((x) => x.id);
  for (let it = 0; it < iterations; it++) {
    const temp = 1 - it / iterations;
    for (const id of ids) { pos[id].dx = 0; pos[id].dy = 0; }
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      const a = pos[ids[i]], b = pos[ids[j]];
      let dx = a.x - b.x, dy = a.y - b.y;
      let d = Math.hypot(dx, dy);
      if (d < 0.01) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d = 0.5; }
      const f = (k * k) / d;
      a.dx += (dx / d) * f; a.dy += (dy / d) * f; b.dx -= (dx / d) * f; b.dy -= (dy / d) * f;
    }
    for (const e of edges) {
      const a = pos[e.source], b = pos[e.target];
      if (!a || !b) continue;
      const dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy) + 0.01;
      const f = (d * d) / k;
      a.dx -= (dx / d) * f; a.dy -= (dy / d) * f; b.dx += (dx / d) * f; b.dy += (dy / d) * f;
    }
    for (const id of ids) {
      const p = pos[id];
      p.dx += (W / 2 - p.x) * 0.3; p.dy += (H / 2 - p.y) * 0.3; // gravity keeps components together
      const d = Math.hypot(p.dx, p.dy) || 1, step = Math.min(d, 8 * temp + 0.3);
      p.x = Math.min(W - 24, Math.max(24, p.x + (p.dx / d) * step));
      p.y = Math.min(H - 24, Math.max(24, p.y + (p.dy / d) * step));
    }
  }
  return Object.fromEntries(ids.map((id) => [id, { x: pos[id].x, y: pos[id].y }]));
}
