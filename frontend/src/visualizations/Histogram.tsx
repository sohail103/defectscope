import type { Histogram as H } from "../types";

export default function Histogram({ data, color = "var(--structural)" }: { data: H[]; color?: string }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="hist" role="img" aria-label={data.map((d) => `${d.label}: ${d.count}`).join(", ")}>
      {data.map((d) => (
        <div className="col" key={d.label} title={`${d.label}: ${d.count}`}>
          <em>{d.count || ""}</em>
          <i style={{ height: `${(d.count / max) * 80}%`, background: color }} />
          <span>{d.label}</span>
        </div>
      ))}
    </div>
  );
}
