export interface Line { name: string; color: string; values: (number | null)[] }

const W = 560, H = 190, M = { l: 44, r: 12, t: 12, b: 28 };

/** Line chart over an ordered list of labels (dates / months). Null values leave gaps. */
export function LineChart({ labels, lines, yLabel }: { labels: string[]; lines: Line[]; yLabel: string }) {
  const all = lines.flatMap((l) => l.values.filter((v): v is number => v !== null));
  const max = Math.max(1, ...all);
  const x = (i: number) => M.l + (labels.length <= 1 ? 0.5 : i / (labels.length - 1)) * (W - M.l - M.r);
  const y = (v: number) => H - M.b - (v / max) * (H - M.t - M.b);
  const ticks = [0, 0.5, 1].map((t) => Math.round(t * max * 10) / 10);
  const every = Math.max(1, Math.ceil(labels.length / 7));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%" }} role="img" aria-label={yLabel + " over time"}>
      {ticks.map((t) => (<g key={t}><line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="#e8ebe8" /><text x={M.l - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="#5d6a75">{t}</text></g>))}
      {labels.map((l, i) => i % every === 0 && <text key={l + i} x={x(i)} y={H - 8} fontSize="10" textAnchor="middle" fill="#5d6a75">{l}</text>)}
      {lines.map((ln) => {
        const pts = ln.values.map((v, i) => (v === null ? null : [x(i), y(v)] as [number, number]));
        const segs: string[] = []; let cur: string[] = [];
        pts.forEach((p) => { if (p) cur.push(p.join(",")); else if (cur.length) { segs.push(cur.join(" ")); cur = []; } });
        if (cur.length) segs.push(cur.join(" "));
        return (<g key={ln.name}>{segs.map((s, i) => <polyline key={i} points={s} fill="none" stroke={ln.color} strokeWidth={2} />)}
          {pts.map((p, i) => p && <circle key={i} cx={p[0]} cy={p[1]} r={3} fill={ln.color}><title>{`${ln.name} ${labels[i]}: ${ln.values[i]}`}</title></circle>)}</g>);
      })}
      <text transform={`translate(11 ${(M.t + H - M.b) / 2}) rotate(-90)`} fontSize="10.5" textAnchor="middle" fill="#16212b">{yLabel}</text>
    </svg>
  );
}

/** Vertical bars with an optional overlaid second series (e.g. all commits vs fix-like commits). */
export function Bars({ labels, values, overlay, color = "var(--history)", overlayColor = "var(--sev-high)" }: {
  labels: string[]; values: number[]; overlay?: number[]; color?: string; overlayColor?: string;
}) {
  const max = Math.max(1, ...values);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 120 }}>
        {values.map((v, i) => (
          <div key={labels[i]} title={`${labels[i]}: ${v}${overlay ? ` (${overlay[i]} fix-like)` : ""}`} style={{ flex: 1, height: "100%", display: "flex", alignItems: "flex-end", position: "relative", minWidth: 0 }}>
            <i style={{ display: "block", width: "100%", height: `${(v / max) * 100}%`, background: color, borderRadius: "2px 2px 0 0", minHeight: v ? 2 : 0 }} />
            {overlay && overlay[i] > 0 && <i style={{ position: "absolute", bottom: 0, left: 0, width: "100%", height: `${(overlay[i] / max) * 100}%`, background: overlayColor, opacity: 0.85 }} />}
          </div>))}
      </div>
      <div style={{ display: "flex", gap: 4 }}>{labels.map((l, i) => <span key={l} style={{ flex: 1, fontSize: 10, color: "var(--muted)", textAlign: "center", overflow: "hidden" }}>{i % Math.ceil(labels.length / 8) === 0 ? l.slice(2) : ""}</span>)}</div>
    </div>
  );
}
