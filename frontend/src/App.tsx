import { useEffect, useState } from "react";
import ImportPage from "./pages/ImportPage";
import ProjectPage from "./pages/ProjectPage";
import LabPage from "./pages/LabPage";

export type Route =
  | { page: "home" }
  | { page: "lab"; tab: string }
  | { page: "project"; id: string; tab: string; params: URLSearchParams };

function parse(): Route {
  const [path, query = ""] = location.hash.replace(/^#/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "p" && parts[1]) return { page: "project", id: parts[1], tab: parts[2] || "overview", params: new URLSearchParams(query) };
  if (parts[0] === "lab") return { page: "lab", tab: parts[1] || "datasets" };
  return { page: "home" };
}
export const go = (path: string) => { location.hash = path; };

export default function App() {
  const [route, setRoute] = useState<Route>(parse());
  useEffect(() => {
    const h = () => setRoute(parse());
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => go("/")} aria-label="DefectScope home">
          <span className="brand-mark" aria-hidden><i/><i/><i/><i/><i/><i/><i/><i/><i/></span>
          DefectScope
        </button>
        <nav className="row" style={{ gap: 4 }}>
          <button className="pill" style={{ background: route.page !== "lab" ? "#2a3846" : "none" }} onClick={() => go("/")}>Projects</button>
          <button className="pill" style={{ background: route.page === "lab" ? "#2a3846" : "none" }} onClick={() => go("/lab/datasets")}>Model lab</button>
        </nav>
        <span className="spacer" />
        <span className="pill" title="All analysis runs on this machine; nothing is sent to external services.">local only</span>
      </header>
      <main className="main">
        {route.page === "home" && <ImportPage />}
        {route.page === "lab" && <LabPage tab={route.tab} />}
        {route.page === "project" && <ProjectPage key={route.id} id={route.id} tab={route.tab} params={route.params} />}
      </main>
    </div>
  );
}
