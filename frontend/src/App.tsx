import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { BiothreatMap } from "./components/Map";
import { OutbreakPanel } from "./components/OutbreakPanel";
import { SourcesPanel } from "./components/SourcesPanel";
import { StateAICard } from "./components/StateAICard";
import { StateDetailPanel } from "./components/StateDetailPanel";
import { BriefingModal } from "./components/BriefingModal";
import type { Domain, Pathogen } from "./types";

type Tab = "map" | "watch" | "sources";

const DOMAINS: Domain[] = ["wastewater", "syndromic"];
const DOMAIN_LABEL: Record<Domain, string> = {
  wastewater: "Wastewater",
  syndromic: "Syndromic",
};
const PATHOGENS: Pathogen[] = ["SARS-CoV-2", "Influenza A", "RSV"];
const TAB_LABEL: Record<Tab, string> = {
  map: "Map",
  watch: "🌐 Global Watch",
  sources: "Data Sources",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("map");
  const [domain, setDomain] = useState<Domain>("wastewater");
  const [pathogen, setPathogen] = useState<Pathogen>("SARS-CoV-2");
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [briefingOpen, setBriefingOpen] = useState(false);

  const { data: geojson } = useQuery({
    queryKey: ["states-geojson"], queryFn: api.statesGeoJson, staleTime: Infinity,
  });
  const { data: statesData } = useQuery({
    queryKey: ["map-states"], queryFn: api.mapStates, staleTime: 5 * 60 * 1000,
  });
  const { data: alertsData, isLoading: alertsLoading } = useQuery({
    queryKey: ["outbreak-alerts"], queryFn: () => api.outbreakAlerts(15), staleTime: 5 * 60 * 1000,
  });
  const { data: sourcesData, isLoading: sourcesLoading } = useQuery({
    queryKey: ["sources"], queryFn: api.sources, staleTime: Infinity,
  });

  const selectedSignals = selectedState ? statesData?.states[selectedState] : undefined;

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      fontFamily: "'Trebuchet MS', Arial, sans-serif", background: "#f6f8fc",
    }}>
      <header style={{
        background: "#1A2744", color: "#fff", padding: "0 24px",
        display: "flex", alignItems: "center", gap: 20, flexShrink: 0, height: 52, flexWrap: "wrap",
      }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Biothreat Radar</div>

        <nav style={{ display: "flex", gap: 2 }}>
          {(["map", "watch", "sources"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: tab === t ? "rgba(255,255,255,0.12)" : "transparent",
                border: "none",
                borderBottom: tab === t ? "2px solid #2E86DE" : "2px solid transparent",
                color: tab === t ? "#fff" : "#7A99B8",
                padding: "0 14px", height: 52, fontSize: 12,
                fontWeight: tab === t ? 700 : 400,
                fontFamily: "'Trebuchet MS', Arial, sans-serif",
                letterSpacing: "0.06em", cursor: "pointer", whiteSpace: "nowrap",
              }}
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </nav>

        {tab === "map" && (
          <>
            <ToggleGroup
              options={DOMAINS.map((d) => ({ v: d, label: DOMAIN_LABEL[d] }))}
              value={domain}
              onChange={(v) => setDomain(v)}
            />
            <ToggleGroup
              options={PATHOGENS.map((p) => ({ v: p, label: p }))}
              value={pathogen}
              onChange={(v) => setPathogen(v)}
            />
          </>
        )}

        <button
          onClick={() => setBriefingOpen(true)}
          style={{
            marginLeft: "auto", background: "#2E86DE", color: "#fff", border: "none",
            borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          Generate Briefing
        </button>
      </header>

      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {tab === "map" && (
          <div style={{ display: "flex", height: "100%", width: "100%" }}>
            <div style={{ flex: "0 0 65%", position: "relative", overflow: "hidden" }}>
              <BiothreatMap
                geojson={geojson}
                statesData={statesData}
                domain={domain}
                pathogen={pathogen}
                selectedState={selectedState}
                onSelectState={setSelectedState}
              />
              <div style={{
                position: "absolute", bottom: 16, left: 16, zIndex: 1000,
                background: "#fff", borderRadius: 8, padding: "10px 14px",
                boxShadow: "0 2px 12px rgba(0,0,0,0.12)", fontSize: 11, maxWidth: 280,
              }}>
                <div style={{ fontWeight: 700, color: "#1A2744", marginBottom: 4 }}>
                  {DOMAIN_LABEL[domain]} — {pathogen}
                </div>
                <div style={{ color: "#7A92AB", lineHeight: 1.5 }}>
                  {domain === "wastewater"
                    ? "Fixed severity scale (Very Low→Very High) — same color means the same thing every week."
                    : "Color scaled to the currently-loaded range for this domain."}
                  {" "}Gray = no data. Click a state for details.
                </div>
              </div>
            </div>

            <div style={{ flex: "0 0 35%", height: "100%", overflowY: "auto", borderLeft: "1px solid #e0e6f0" }}>
              {selectedState ? (
                <div style={{ padding: 16 }}>
                  <StateAICard state={selectedState} />
                  <StateDetailPanel stateName={selectedState} signals={selectedSignals} />
                </div>
              ) : (
                <div style={{ padding: 16, fontSize: 12, color: "#7A92AB" }}>
                  Click a state on the map to see its wastewater, syndromic, and genomic trends,
                  plus an AI analysis of anything notable.
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "watch" && <OutbreakPanel alerts={alertsData?.alerts} isLoading={alertsLoading} />}
        {tab === "sources" && <SourcesPanel sources={sourcesData?.sources} isLoading={sourcesLoading} />}
      </div>

      {briefingOpen && (
        <BriefingModal defaultState={selectedState} onClose={() => setBriefingOpen(false)} />
      )}
    </div>
  );
}

function ToggleGroup<T extends string>({
  options, value, onChange,
}: {
  options: { v: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6,
      background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.15)",
      borderRadius: 6, padding: "0 4px", height: 32,
    }}>
      {options.map(({ v, label }) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          style={{
            background: value === v ? "#2E86DE" : "transparent",
            color: value === v ? "#fff" : "#7A99B8",
            border: "none", borderRadius: 4, padding: "0 10px", height: 24,
            fontSize: 11, fontWeight: 700, letterSpacing: "0.04em", cursor: "pointer",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
