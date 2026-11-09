import { useCallback, useEffect, useState } from "react";
import { api, pollJob, post } from "../api";
import { go } from "../App";
import type { AnalysisConfig, AnalysisOverview, Job, ProjectDetail } from "../types";
import OverviewTab from "../features/OverviewTab";
import ExplorerTab from "../features/ExplorerTab";
import GraphTab from "../features/GraphTab";
import SetupTab from "../features/SetupTab";
import RiskTab from "../features/RiskTab";

export interface ProjectCtx {
  id: string; detail: ProjectDetail; overview: AnalysisOverview | null;
  config: AnalysisConfig | null; setConfig: (c: AnalysisConfig) => void;
  job: Job | null; running: boolean; run: () => void; cancel: () => void;
  open: (path: string, line?: number) => void; reload: () => void;
}

const TABS = [
  ["overview", "Overview"], ["explorer", "Explorer"], ["graph", "Dependencies"],
  ["risk", "Defect risk"], ["setup", "Analysis setup"],
] as const;

export default function ProjectPage({ id, tab, params }: { id: string; tab: string; params: URLSearchParams }) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [overview, setOverview] = useState<AnalysisOverview | null>(null);
  const [config, setConfig] = useState<AnalysisConfig | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api<ProjectDetail>(`/projects/${id}`);
      setDetail(d);
      setOverview(d.latest_analysis ? await api<AnalysisOverview>(`/projects/${id}/analysis`) : null);
    } catch (e: any) { setError(e.message); }
  }, [id]);
  useEffect(() => { load(); api<AnalysisConfig>("/config/defaults").then(setConfig); }, [load]);

  const running = !!job && ["queued", "running"].includes(job.status);
  const run = async () => {
    setError(null);
    try {
      const j = await post<Job>(`/projects/${id}/analyze`, config ?? undefined);
      setJob(j);
      const done = await pollJob(j.id, setJob);
      if (done.status === "failed") setError(done.error || "Analysis failed");
      await load();
      if (done.status === "done" && tab === "setup") go(`/p/${id}/overview`);
    } catch (e: any) { setError(e.message); }
  };
  const cancel = () => job && post(`/jobs/${job.id}/cancel`);
  const open = (path: string, line?: number) => go(`/p/${id}/explorer?file=${encodeURIComponent(path)}${line ? `&line=${line}` : ""}`);

  if (error && !detail) return <div className="page"><div className="notice error">{error}</div></div>;
  if (!detail) return <div className="page muted">Loading project…</div>;
  const ctx: ProjectCtx = { id, detail, overview, config, setConfig, job, running, run, cancel, open, reload: load };

  return (
    <>
      <div className="tabs" role="tablist">
        <span style={{ alignSelf: "center", fontWeight: 600, marginRight: 14 }}>{detail.meta.name}</span>
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => go(`/p/${id}/${k}`)}>{label}</button>
        ))}
        <span style={{ flex: 1 }} />
        {overview?.stale && <span className="badge sev-warning" style={{ alignSelf: "center", marginRight: 10 }}>analysis is stale</span>}
        {running ? (
          <span className="row" style={{ alignSelf: "center", gap: 10 }}>
            <span className="small muted">{Math.round((job?.progress ?? 0) * 100)}% · {job?.message}</span>
            <button className="btn small" onClick={cancel}>Cancel</button>
          </span>
        ) : (
          <button className="btn primary small" style={{ alignSelf: "center" }} onClick={run}>{overview ? "Re-run analysis" : "Run analysis"}</button>
        )}
      </div>
      {running && <div className="bar" style={{ borderRadius: 0, height: 3 }}><i style={{ width: `${(job?.progress ?? 0) * 100}%` }} /></div>}
      {error && <div className="page" style={{ paddingBottom: 0 }}><div className="notice error">{error}</div></div>}
      {tab === "overview" && <OverviewTab ctx={ctx} />}
      {tab === "explorer" && <ExplorerTab ctx={ctx} params={params} />}
      {tab === "graph" && <GraphTab ctx={ctx} />}
      {tab === "risk" && <RiskTab ctx={ctx} />}
      {tab === "setup" && <SetupTab ctx={ctx} />}
    </>
  );
}
