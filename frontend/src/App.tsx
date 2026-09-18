import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { BiothreatMap } from "./components/Map";
import { OutbreakPanel } from "./components/OutbreakPanel";
import { SourcesPanel } from "./components/SourcesPanel";
import type { Domain } from "./types";

type Tab = "map" | "sources";

const DOMAINS: Domain[] = ["wastewater", "syndromic", "genomic"];
const DOMAIN_LABEL: Record<Domain, string> = {
  wastewater: "Wastewater",
  syndromic: "Syndromic",
  genomic: "Genomic",
};

export default function App() {
  const [tab, setTab] = useState<Tab>("map");
  const [domain, setDomain] = useState<Domain>("wastewater");
  const [selectedState, setSelectedState] = useState<string | null>(null);

  const { data: geojson } = useQuery({
    queryKey: ["states-geojson"],
    queryFn: api.statesGeoJson,
    staleTime: Infinity,
  });
  const { data: statesData } = useQuery({
    queryKey: ["map-states"],
    queryFn: api.mapStates,
    staleTime: 5 * 60 * 1000,
  });
  const { data: airportsData } = useQuery({
    queryKey: ["map-airports"],
    queryFn: api.mapAirports,
    staleTime: 5 * 60 * 1000,
  });
  const { data: alertsData, isLoading: alertsLoading } = useQuery({
    queryKey: ["outbreak-alerts"],
    queryFn: () => api.outbreakAlerts(15),
    staleTime: 5 * 60 * 1000,
  });
  const { data: sourcesData, isLoading: sourcesLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: api.sources,
    staleTime: Infinity,
  });

  const selectedSignals = selectedState ? statesData?.states[selectedState] : undefined;

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      fontFamily: "'Trebuchet MS', Arial, sans-serif", background: "#f6f8fc",
    }}>
      {/* Header */}
      <header style={{
        background: "#1A2744", color: "#fff", padding: "0 24px",
        display: "flex", alignItems: "center", gap: 24, flexShrink: 0, height: 52,
      }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Biothreat Radar</div>

        <nav style={{ display: "flex", gap: 2, marginLeft: 16 }}>
          {(["map", "sources"] as Tab[]).map((t) => (
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
                letterSpacing: "0.06em", cursor: "pointer",
              }}
            >
              {t === "map" ? "Map" : "Data Sources"}
            </button>
          ))}
        </nav>

        {tab === "map" && (
          <div style={{
            display: "flex", alignItems: "center", gap: 6, marginLeft: "auto",
            background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.15)",
            borderRadius: 6, padding: "0 4px", height: 32,
          }}>
            {DOMAINS.map((d) => (
              <button
                key={d}
                onClick={() => setDomain(d)}
                style={{
                  background: domain === d ? "#2E86DE" : "transparent",
                  color: domain === d ? "#fff" : "#7A99B8",
                  border: "none", borderRadius: 4, padding: "0 10px", height: 24,
                  fontSize: 11, fontWeight: 700, letterSpacing: "0.04em", cursor: "pointer",
                }}
              >
                {DOMAIN_LABEL[d]}
              </button>
            ))}
          </div>
        )}
      </header>

      {/* Body */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {tab === "map" && (
          <div style={{ display: "flex", height: "100%", width: "100%" }}>
            <div style={{ flex: "0 0 65%", position: "relative", overflow: "hidden" }}>
              <BiothreatMap
                geojson={geojson}
                statesData={statesData}
                airports={airportsData?.airports ?? []}
                domain={domain}
                selectedState={selectedState}
                onSelectState={setSelectedState}
              />
              <div style={{
                position: "absolute", bottom: 16, left: 16, zIndex: 1000,
                background: "#fff", borderRadius: 8, padding: "10px 14px",
                boxShadow: "0 2px 12px rgba(0,0,0,0.12)", fontSize: 11, maxWidth: 260,
              }}>
                <div style={{ fontWeight: 700, color: "#1A2744", marginBottom: 4 }}>
                  {DOMAIN_LABEL[domain]} — SARS-CoV-2
                </div>
                <div style={{ color: "#7A92AB", lineHeight: 1.5 }}>
                  Color scaled to the currently-loaded range for this domain.
                  Blue circles = international arrivals by airport.
                  Gray = no data. Click a state for details.
                </div>
              </div>
            </div>

            <div style={{ flex: "0 0 35%", height: "100%", overflowY: "auto", borderLeft: "1px solid #e0e6f0" }}>
              {selectedState && (
                <div style={{ padding: 16, borderBottom: "1px solid #e8eef6" }}>
                  <h3 style={{ margin: "0 0 8px", fontSize: 14, color: "#1A2744" }}>{selectedState}</h3>
                  {DOMAINS.map((d) => {
                    const sig = selectedSignals?.[d];
                    return (
                      <div key={d} style={{ fontSize: 12, margin: "4px 0", color: "#333" }}>
                        <strong>{DOMAIN_LABEL[d]}:</strong>{" "}
                        {sig ? `${sig.value.toFixed(3)} (${sig.period_end}, ${sig.granularity})` : "no data"}
                      </div>
                    );
                  })}
                </div>
              )}
              <OutbreakPanel alerts={alertsData?.alerts} isLoading={alertsLoading} />
            </div>
          </div>
        )}

        {tab === "sources" && <SourcesPanel sources={sourcesData?.sources} isLoading={sourcesLoading} />}
      </div>
    </div>
  );
}
