import { useEffect, useState } from "react";
import type { TreeNode } from "../types";

function filterTree(n: TreeNode, q: string): TreeNode | null {
  if (!q) return n;
  if (n.type === "file") return n.path.toLowerCase().includes(q) ? n : null;
  const kids = (n.children ?? []).map((c) => filterTree(c, q)).filter(Boolean) as TreeNode[];
  return kids.length ? { ...n, children: kids } : null;
}

export default function FileTree({ root, selected, onSelect }: { root: TreeNode; selected?: string; onSelect: (p: string) => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Set<string>>(new Set([""]));
  useEffect(() => {
    if (!selected) return;
    setOpen((o) => {
      const n = new Set(o); const parts = selected.split("/");
      for (let i = 1; i < parts.length; i++) n.add(parts.slice(0, i).join("/"));
      return n;
    });
  }, [selected]);
  const tree = filterTree(root, q.trim().toLowerCase());

  const render = (n: TreeNode, depth: number): JSX.Element[] => {
    const pad = { paddingLeft: 8 + depth * 14 };
    if (n.type === "file") {
      const hi = (n.max_cyclomatic ?? 0) >= 20;
      return [
        <div key={n.path} className={"tree-row" + (selected === n.path ? " sel" : "") + (n.excluded ? " excluded" : "")} style={pad}
          title={n.excluded ? `Excluded: ${n.excluded}` : n.path}
          onClick={() => !n.excluded && n.language && onSelect(n.path)}>
          <span className="chev" />
          {n.language ? <span className={"lang " + n.language} style={{ marginRight: 0 }} /> : <span style={{ width: 8 }} />}
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{n.name}</span>
          {n.max_cyclomatic ? <span className={"chip" + (hi ? " hi" : "")} title="highest cyclomatic complexity in this file">{n.max_cyclomatic}</span> : null}
        </div>,
      ];
    }
    if (n.path === "") return (n.children ?? []).flatMap((c) => render(c, 0));
    const isOpen = q ? true : open.has(n.path);
    const row = (
      <div key={n.path} className={"tree-row" + (n.excluded ? " excluded" : "")} style={pad} title={n.excluded ? `Excluded: ${n.excluded}` : n.path}
        onClick={() => !n.excluded && setOpen((o) => { const x = new Set(o); x.has(n.path) ? x.delete(n.path) : x.add(n.path); return x; })}>
        <span className="chev">{n.excluded ? "·" : isOpen ? "▾" : "▸"}</span>
        <span>{n.name}</span>
        {n.excluded && <span className="chip" style={{ background: "transparent", color: "var(--faint)" }}>{n.excluded}</span>}
      </div>
    );
    return isOpen && !n.excluded ? [row, ...(n.children ?? []).flatMap((c) => render(c, depth + 1))] : [row];
  };

  return (
    <>
      <div className="treefilter"><input className="input" placeholder="Filter files…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter files" /></div>
      <div className="tree">{tree ? render(tree, 0) : <div className="muted small" style={{ padding: 12 }}>No files match.</div>}</div>
    </>
  );
}
