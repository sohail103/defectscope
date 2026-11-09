import { useEffect, useMemo, useRef, useState } from "react";

export interface TmFile { path: string; sloc: number; cc: number }
interface Node { name: string; path: string; value: number; cc: number; children: Node[]; file: boolean }
interface Box { x: number; y: number; w: number; h: number }
interface Cell extends Box { node: Node; dir: boolean }

export const ccColor = (cc: number) =>
  cc >= 21 ? "#a63d17" : cc >= 11 ? "#c9871f" : cc >= 6 ? "#e5b85c" : cc >= 3 ? "#efdba6" : "#f3ecd8";

function build(files: TmFile[]): Node {
  const root: Node = { name: "", path: "", value: 0, cc: 0, children: [], file: false };
  for (const f of files) {
    let cur = root;
    const parts = f.path.split("/");
    parts.forEach((p, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let nxt = cur.children.find((c) => c.name === p);
      if (!nxt) { nxt = { name: p, path, value: 0, cc: 0, children: [], file: i === parts.length - 1 }; cur.children.push(nxt); }
      nxt.value += Math.max(1, f.sloc);
      nxt.cc = Math.max(nxt.cc, f.cc);
      cur = nxt;
    });
  }
  // collapse single-child directory chains for readability
  const collapse = (n: Node): Node => {
    n.children = n.children.map(collapse);
    while (!n.file && n.children.length === 1 && !n.children[0].file && n.name) {
      const c = n.children[0]; n.name += "/" + c.name; n.path = c.path; n.children = c.children;
    }
    return n;
  };
  return collapse(root);
}

function squarify(values: number[], b: Box): Box[] {
  const total = values.reduce((a, c) => a + c, 0);
  if (total <= 0 || b.w <= 0 || b.h <= 0) return values.map(() => ({ x: b.x, y: b.y, w: 0, h: 0 }));
  const areas = values.map((v) => (v / total) * b.w * b.h);
  const out: Box[] = [];
  let { x, y, w, h } = b;
  let row: number[] = [];
  const worst = (r: number[], side: number) => {
    const s = r.reduce((a, c) => a + c, 0), mx = Math.max(...r), mn = Math.min(...r);
    return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
  };
  const flush = () => {
    const s = row.reduce((a, c) => a + c, 0);
    if (w >= h) { const cw = s / h; let yy = y; row.forEach((a) => { const ch = a / cw; out.push({ x, y: yy, w: cw, h: ch }); yy += ch; }); x += cw; w -= cw; }
    else { const rh = s / w; let xx = x; row.forEach((a) => { const cw2 = a / rh; out.push({ x: xx, y, w: cw2, h: rh }); xx += cw2; }); y += rh; h -= rh; }
    row = [];
  };
  for (const a of areas) {
    const side = Math.min(w, h);
    if (row.length === 0 || worst([...row, a], side) <= worst(row, side)) row.push(a);
    else { flush(); row.push(a); }
  }
  if (row.length) flush();
  return out;
}

function layout(n: Node, b: Box, depth: number, out: Cell[]) {
  const kids = [...n.children].sort((a, b2) => b2.value - a.value);
  const boxes = squarify(kids.map((k) => k.value), b);
  kids.forEach((k, i) => {
    const bx = boxes[i];
    if (bx.w < 2 || bx.h < 2) return;
    if (k.file) out.push({ ...bx, node: k, dir: false });
    else {
      out.push({ ...bx, node: k, dir: true });
      const head = bx.h > 40 && bx.w > 50 ? 14 : 0;
      layout(k, { x: bx.x + 1, y: bx.y + head, w: bx.w - 2, h: bx.h - head - 1 }, depth + 1, out);
    }
  });
}

export default function Treemap({ files, onOpen }: { files: TmFile[]; onOpen: (path: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const H = 420;
  const cells = useMemo(() => {
    const out: Cell[] = [];
    layout(build(files), { x: 0, y: 0, w, h: H }, 0, out);
    return out;
  }, [files, w]);
  return (
    <div className="treemap" ref={ref} style={{ height: H }}>
      {cells.map((c) => (
        <div key={c.node.path + (c.dir ? "/" : "")} className={"tm" + (c.dir ? " dir" : "")}
          style={{ left: c.x, top: c.y, width: c.w, height: c.h, background: c.dir ? undefined : ccColor(c.node.cc) }}
          title={c.dir ? c.node.path : `${c.node.path}\nSLOC ${c.node.value}\nmax cyclomatic ${c.node.cc}`}
          onClick={() => !c.dir && onOpen(c.node.path)}>
          {c.dir ? (c.h > 40 && c.w > 50 ? <div className="lbl">{c.node.name}</div> : null) : (c.w > 60 && c.h > 28 ? c.node.name : null)}
        </div>
      ))}
    </div>
  );
}
