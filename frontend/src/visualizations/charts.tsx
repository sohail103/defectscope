import type { ReactNode } from "react";

export interface Series { name: string; color: string; points: [number, number][]; dashed?: boolean }
const W = 360, H = 300, M = { l: 40, r: 12, t: 10, b: 36 };

/** Square [0,1]x[0,1] curve plot (ROC, PR, reliability). */
export function CurvePlot({ series, xLabel, yLabel, diagonal = false }: { series: Series[]; xLabel: string; yLabel: string; diagonal?: boolean }) {
  const x = (v: number) => M.l + v * (W - M.l - M.r);
  const y = (v: number) => H - M.b - v * (H - M.t - M.b);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", maxWidth: 420 }} role="img" aria-label={`${yLabel} versus ${xLabel}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="#e8ebe8" />
          <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke="#e8ebe8" />
          <text x={x(0) - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="#5d6a75">{t}</text>
          <text x={x(t)} y={H - M.b + 14} fontSize="10" textAnchor="middle" fill="#5d6a75">{t}</text>
        </g>
      ))}
      {diagonal && <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#8a95a0" strokeDasharray="4 3" />}
      {series.map((s) => (
        <polyline key={s.name} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "5 3" : undefined}
          points={s.points.map(([a, b]) => `${x(a)},${y(b)}`).join(" ")} />
      ))}
      {series.map((s) => s.points.length <= 14 && s.points.map(([a, b], i) => <circle key={s.name + i} cx={x(a)} cy={y(b)} r={3} fill={s.color} />))}
      <text x={(M.l + W - M.r) / 2} y={H - 4} fontSize="11" textAnchor="middle" fill="#16212b">{xLabel}</text>
      <text transform={`translate(11 ${(M.t + H - M.b) / 2}) rotate(-90)`} fontSize="11" textAnchor="middle" fill="#16212b">{yLabel}</text>
    </svg>
  );
}

export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return <div className="legend" style={{ marginTop: 6 }}>{items.map((i) => <span key={i.name}><i style={{ display: "inline-block", width: 14, height: 3, background: i.color, marginRight: 5, verticalAlign: 3 }} />{i.name}</span>)}</div>;
}

/** Horizontal bars with optional ± error and signed values. */
export function HBars({ rows, max, signed = false, fmt = (v: number) => v.toFixed(3) }: {
  rows: { label: ReactNode; value: number; err?: number; color?: string; note?: ReactNode }[]; max?: number; signed?: boolean; fmt?: (v: number) => string;
}) {
  const m = max ?? Math.max(1e-9, ...rows.map((r) => Math.abs(r.value) + (r.err ?? 0)));
  return (
    <div className="grid" style={{ gap: 5 }}>
      {rows.map((r, i) => {
        const w = (Math.abs(r.value) / m) * (signed ? 50 : 100);
        const left = signed ? (r.value >= 0 ? 50 : 50 - w) : 0;
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(110px, 190px) 1fr 70px", gap: 8, alignItems: "center", fontSize: 12.5 }}>
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={typeof r.label === "string" ? r.label : undefined}>{r.label}</span>
            <span style={{ position: "relative", height: 12, background: "var(--rule-soft)", borderRadius: 3 }}>
              {signed && <i style={{ position: "absolute", left: "50%", top: -2, bottom: -2, width: 1, background: "var(--faint)" }} />}
              <i style={{ position: "absolute", left: `${left}%`, width: `${w}%`, top: 0, bottom: 0, background: r.color ?? (signed && r.value < 0 ? "var(--history)" : "var(--structural)"), borderRadius: 3 }} />
              {r.err ? <i style={{ position: "absolute", left: `calc(${left + w}% - 0px)`, width: `${(r.err / m) * (signed ? 50 : 100)}%`, top: 5, height: 2, background: "var(--ink)" }} /> : null}
            </span>
            <span className="mono" style={{ textAlign: "right" }}>{fmt(r.value)}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Scatter with log-ish x axis and a binary y (0/1 with jitter). */
export function BinaryScatter({ points, xLabel }: { points: { x: number; y: number }[]; xLabel: string }) {
  const W2 = 520, H2 = 150, ml = 62;
  const xs = points.map((p) => Math.log1p(Math.max(0, p.x)));
  const mx = Math.max(1e-9, ...xs);
  const jit = (i: number) => ((Math.sin(i * 12.9898) * 43758.5453) % 1 + 1) % 1;
  return (
    <svg viewBox={`0 0 ${W2} ${H2 + 28}`} style={{ width: "100%" }} role="img" aria-label={`${xLabel} against defect label`}>
      <text x={ml - 8} y={32} fontSize="10" textAnchor="end" fill="#a8223b">defective</text>
      <text x={ml - 8} y={H2 - 22} fontSize="10" textAnchor="end" fill="#5d6a75">clean</text>
      <line x1={ml} x2={W2 - 6} y1={H2 / 2} y2={H2 / 2} stroke="#e8ebe8" />
      {points.map((p, i) => {
        const cx = ml + (xs[i] / mx) * (W2 - ml - 10);
        const base = p.y ? 30 : H2 - 30;
        return <circle key={i} cx={cx} cy={base + (jit(i) - 0.5) * 36} r={2.4} fill={p.y ? "#a8223b" : "#5d6a75"} opacity={p.y ? 0.55 : 0.28} />;
      })}
      <text x={(ml + W2) / 2} y={H2 + 20} fontSize="11" textAnchor="middle" fill="#16212b">{xLabel} (log scale)</text>
    </svg>
  );
}
