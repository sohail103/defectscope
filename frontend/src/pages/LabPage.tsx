import { go } from "../App";
import DatasetsTab from "../model-lab/DatasetsTab";
import ExperimentsTab from "../model-lab/ExperimentsTab";
import ModelsTab from "../model-lab/ModelsTab";

const TABS = [["datasets", "Datasets"], ["experiments", "Experiments"], ["models", "Models"]] as const;

export default function LabPage({ tab }: { tab: string }) {
  return (
    <>
      <div className="tabs" role="tablist">
        <span style={{ alignSelf: "center", fontWeight: 600, marginRight: 14 }}>Model lab</span>
        {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => go(`/lab/${k}`)}>{label}</button>)}
      </div>
      {tab === "datasets" && <DatasetsTab />}
      {tab === "experiments" && <ExperimentsTab />}
      {tab === "models" && <ModelsTab />}
    </>
  );
}
