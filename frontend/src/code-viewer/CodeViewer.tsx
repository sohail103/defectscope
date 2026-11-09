import { memo, useEffect, useMemo, useRef } from "react";
import type { Entity, Hotspot, Severity } from "../types";
import type { Prediction } from "../types/lab";
import { highlightLines } from "./highlight";

export interface Layers { heat: boolean; structural: boolean; staticAnalysis: boolean; risk: boolean }
const SEV: Record<Severity, number> = { info: 1, warning: 2, high: 3 };
const SEV_NAME: Severity[] = ["info", "info", "warning", "high"];
const LH = 20;

interface RowProps {
  n: number; html: string; sev: number; tip: string; heat: number; inSel: boolean; decision: boolean;
  flash: boolean; riskTip: string; riskOn: boolean; onPick: (n: number) => void;
}
const Row = memo(function Row({ n, html, sev, tip, heat, inSel, decision, flash, riskTip, riskOn, onPick }: RowProps) {
  return (
    <div className={"ln" + (inSel ? " in-sel" : "") + (decision ? " decision" : "") + (flash ? " flash" : "")} data-line={n} onClick={() => onPick(n)}>
      <span className="num">{n}</span>
      <span className={"lane s" + (sev ? " " + SEV_NAME[sev] : "")} title={tip} />
      <span className="lane d" />
      <span className="lane r">{riskTip ? <i className={"tri" + (riskOn ? " on" : "")} title={riskTip} /> : null}</span>
      <span className="src" style={heat ? { background: `rgba(169,106,16,${heat})` } : undefined} dangerouslySetInnerHTML={{ __html: html || " " }} />
    </div>
  );
});

export default function CodeViewer(props: {
  content: string; language?: string | null; entities: Entity[]; hotspots: Hotspot[]; layers: Layers;
  selected: Entity | null; targetLine?: number; onSelect: (e: Entity | null) => void; predictions?: Prediction[]; modelName?: string;
}) {
  const { content, language, entities, hotspots, layers, selected, targetLine, onSelect, predictions = [], modelName = "model" } = props;
  const riskByLine = useMemo(() => new Map(predictions.map((p) => [p.start_line, p])), [predictions]);
  const scroller = useRef<HTMLDivElement>(null);
  const html = useMemo(() => highlightLines(content, language), [content, language]);
  const funcs = useMemo(() => entities.filter((e) => e.kind === "function"), [entities]);

  // Per-line structural data, derived from real hotspot ranges and function complexity.
  const lineData = useMemo(() => {
    const n = html.length;
    const sev = new Array(n + 2).fill(0);
    const tips: string[][] = Array.from({ length: n + 2 }, () => []);
    for (const h of hotspots) {
      if (h.layer !== "structural") continue;
      for (let l = h.range.start_line; l <= Math.min(h.range.end_line, n); l++) {
        sev[l] = Math.max(sev[l], SEV[h.severity]);
        if (l === h.range.start_line) tips[l].push(`[${h.severity}] ${h.message}`);
      }
    }
    const heat = new Array(n + 2).fill(0);
    [...funcs].sort((a, b) => (b.range.end_line - b.range.start_line) - (a.range.end_line - a.range.start_line)).forEach((f) => {
      const cc = f.metrics.cyclomatic ?? 1;
      const a = cc <= 1 ? 0 : Math.min(0.22, 0.03 + (cc / 25) * 0.2);
      for (let l = f.range.start_line; l <= Math.min(f.range.end_line, n); l++) heat[l] = a;
    });
    return { sev, tips, heat };
  }, [html.length, hotspots, funcs]);

  const decisionLines = useMemo(() => {
    const s = new Set<number>();
    if (selected?.kind === "function") for (const c of selected.details.contributor_lines ?? []) s.add(c.line);
    return s;
  }, [selected]);

  const pick = (line: number) => {
    const inner = [...entities].filter((e) => e.kind !== "file" && e.range.start_line <= line && line <= e.range.end_line)
      .sort((a, b) => (a.range.end_line - a.range.start_line) - (b.range.end_line - b.range.start_line))[0];
    onSelect(inner ?? null);
  };

  useEffect(() => {
    const line = targetLine ?? selected?.range.start_line;
    if (line && scroller.current) scroller.current.scrollTop = Math.max(0, (line - 4) * LH);
  }, [targetLine, selected?.id, content]);

  return (
    <div className="code" ref={scroller}>
      {html.map((h, i) => {
        const n = i + 1;
        const inSel = !!selected && selected.kind !== "file" && n >= selected.range.start_line && n <= selected.range.end_line;
        return (
          <Row key={n} n={n} html={h}
            sev={layers.structural ? lineData.sev[n] : 0}
            tip={layers.structural ? lineData.tips[n].join("\n") : ""}
            heat={layers.heat ? lineData.heat[n] : 0}
            inSel={inSel} decision={decisionLines.has(n)} flash={!!targetLine && n === targetLine} onPick={pick}
            riskTip={layers.risk && riskByLine.get(n) ? `Predicted risk ${(riskByLine.get(n)!.probability * 100).toFixed(0)}% for this whole function (${modelName}). Function-level estimate, not a line-level finding.` : ""}
            riskOn={!!riskByLine.get(n)?.flagged} />
        );
      })}
    </div>
  );
}
