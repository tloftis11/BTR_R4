import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { StatesResponse, Airport, Domain, Pathogen, StateSignals, ViewMode } from "../types";

const NO_DATA_STYLE: L.PathOptions = {
  color: "#b0bec5", weight: 0.5, fillColor: "#eceff1", fillOpacity: 0.4,
};
const MUTED_STYLE: L.PathOptions = {
  color: "#cfd8e3", weight: 0.6, fillColor: "#f6f8fc", fillOpacity: 0.5,
};

// CDC's own category labels, in severity order -- used both for the fixed
// 0-4 map color scale and for rendering the distribution chips.
const WASTEWATER_CATEGORIES = ["Very Low", "Low", "Moderate", "High", "Very High"];
const WASTEWATER_ORDINAL: Record<string, number> = Object.fromEntries(
  WASTEWATER_CATEGORIES.map((c, i) => [c, i]),
);

function rampColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const stops: [number, string][] = [
    [0, "#ffffcc"], [0.25, "#fed976"], [0.5, "#fd8d3c"], [0.75, "#e31a1c"], [1, "#800026"],
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (clamped >= t0 && clamped <= t1) return lerpColor(c0, c1, (clamped - t0) / (t1 - t0));
  }
  return stops[stops.length - 1][1];
}

function lerpColor(a: string, b: string, t: number): string {
  const pa = hexToRgb(a), pb = hexToRgb(b);
  const r = Math.round(pa[0] + (pb[0] - pa[0]) * t);
  const g = Math.round(pa[1] + (pb[1] - pa[1]) * t);
  const bl = Math.round(pa[2] + (pb[2] - pa[2]) * t);
  return `rgb(${r},${g},${bl})`;
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const TREND_ARROW: Record<string, string> = { rising: "↑", falling: "↓", stable: "→" };

/** Wastewater's severity is a fixed 0-4 scale (weighted avg of site
 * categories) -- "Very High" means the same color every week, not relative
 * to whatever's currently loaded. Syndromic/genomic don't have an
 * authoritative fixed breakpoint, so those stay relative to the loaded range.
 */
function wastewaterSeverity(dist: Record<string, number>): number | null {
  const total = Object.values(dist).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  const weighted = Object.entries(dist).reduce(
    (sum, [cat, count]) => sum + (WASTEWATER_ORDINAL[cat] ?? 2) * count, 0,
  );
  return weighted / total;
}

function colorValueFor(domain: Domain, pathogen: Pathogen, sig: StateSignals | undefined): number | null {
  if (!sig) return null;
  if (domain === "wastewater") {
    const w = sig.wastewater[pathogen];
    return w ? wastewaterSeverity(w.category_distribution) : null;
  }
  if (domain === "syndromic") {
    return sig.syndromic[pathogen]?.percent_ed_visits ?? null;
  }
  // genomic: color by how fast the leading mover is climbing (the
  // emerging-threat signal), falling back to the leader's raw share when
  // there's only one period loaded and no delta is computable yet.
  return sig.genomic?.fastest_growing?.change ?? sig.genomic?.current_leader?.share ?? null;
}

function tooltipFor(domain: Domain, pathogen: Pathogen, stateName: string, sig: StateSignals | undefined): string {
  if (domain === "wastewater") {
    const w = sig?.wastewater[pathogen];
    if (!w) return `<strong>${stateName}</strong><br/>No wastewater data for ${pathogen}`;
    const chips = WASTEWATER_CATEGORIES
      .filter((c) => w.category_distribution[c])
      .map((c) => `${c}: ${w.category_distribution[c]}`)
      .join(" &middot; ");
    return `<strong>${stateName}</strong><br/>${pathogen} wastewater (${w.site_count} sites)<br/>${chips}` +
      `<br/>Trend: ${TREND_ARROW[w.trend] ?? ""} ${w.trend}` +
      `<br/><span style="color:#888">as of ${w.period_end}</span>`;
  }
  if (domain === "syndromic") {
    const s = sig?.syndromic[pathogen];
    if (!s) return `<strong>${stateName}</strong><br/>No syndromic data for ${pathogen}`;
    return `<strong>${stateName}</strong><br/>${pathogen}: <strong>${s.percent_ed_visits}%</strong> of ED visits` +
      (s.trend ? `<br/>Trend: ${s.trend}` : "") +
      `<br/><span style="color:#888">as of ${s.period_end}</span>`;
  }
  const g = sig?.genomic;
  if (!g) return `<strong>${stateName}</strong><br/>No genomic data`;
  const fg = g.fastest_growing;
  return `<strong>${stateName}</strong><br/>Leading variant: <strong>${g.current_leader.variant}</strong> (${(g.current_leader.share * 100).toFixed(0)}%)` +
    (fg ? `<br/>Fastest growing: <strong>${fg.variant}</strong> (+${(fg.change! * 100).toFixed(0)} pts)` : "") +
    `<br/><span style="color:#888">as of ${g.period_end} &middot; HHS-region shared</span>`;
}

interface Props {
  geojson: GeoJSON.FeatureCollection | undefined;
  statesData: StatesResponse | undefined;
  airports: Airport[];
  viewMode: ViewMode;
  domain: Domain;
  pathogen: Pathogen;
  selectedState: string | null;
  onSelectState: (name: string) => void;
}

export function BiothreatMap({
  geojson, statesData, airports, viewMode, domain, pathogen, selectedState, onSelectState,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const stateLayerRef = useRef<L.GeoJSON | null>(null);
  const airportLayerRef = useRef<L.LayerGroup | null>(null);
  const selectedRef = useRef<string | null>(selectedState);

  useEffect(() => { selectedRef.current = selectedState; }, [selectedState]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current, { center: [39.5, -98.5], zoom: 4, zoomSnap: 0.5 });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      opacity: 0.35,
    }).addTo(mapRef.current);
    return () => { mapRef.current?.remove(); mapRef.current = null; };
  }, []);

  // State choropleth: only in state view, colored by domain+pathogen. In
  // airport view it's rendered muted (outlines only) for geographic context.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !geojson) return;

    if (stateLayerRef.current) {
      map.removeLayer(stateLayerRef.current);
      stateLayerRef.current = null;
    }

    let min = 0, max = 1;
    if (viewMode === "state" && statesData) {
      const values: number[] = [];
      for (const sig of Object.values(statesData.states)) {
        const v = colorValueFor(domain, pathogen, sig);
        if (v !== null) values.push(v);
      }
      if (domain === "wastewater") {
        min = 0; max = 4; // fixed scale -- see colorValueFor/wastewaterSeverity
      } else if (values.length) {
        min = Math.min(...values); max = Math.max(...values) || 1;
      }
    }
    const range = max - min || 1;

    stateLayerRef.current = L.geoJSON(geojson, {
      style: (feature) => {
        if (viewMode === "airport") return MUTED_STYLE;
        const name = feature?.properties?.name as string | undefined;
        const sig = name ? statesData?.states[name] : undefined;
        const value = colorValueFor(domain, pathogen, sig);
        if (value === null) return NO_DATA_STYLE;
        return {
          color: "#fff",
          weight: name === selectedRef.current ? 2.5 : 0.8,
          fillColor: rampColor((value - min) / range),
          fillOpacity: 0.8,
        };
      },
      onEachFeature: (feature, layer) => {
        const name = feature.properties?.name as string | undefined;
        if (viewMode === "state") {
          const sig = name ? statesData?.states[name] : undefined;
          layer.bindTooltip(name ? tooltipFor(domain, pathogen, name, sig) : "", { sticky: true, opacity: 0.95 });
          layer.on("click", () => name && onSelectState(name));
          layer.on("mouseover", function () { (this as L.Path).setStyle({ weight: 2, color: "#1A2744" }); });
          layer.on("mouseout", function () { stateLayerRef.current?.resetStyle(this as L.Path); });
        } else {
          layer.bindTooltip(name ?? "", { sticky: true, opacity: 0.7 });
        }
      },
    }).addTo(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geojson, statesData, domain, pathogen, viewMode]);

  // Airport markers: only in airport view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (airportLayerRef.current) {
      map.removeLayer(airportLayerRef.current);
      airportLayerRef.current = null;
    }
    if (viewMode !== "airport" || !airports.length) return;

    const maxPax = Math.max(...airports.map((a) => a.inbound_passengers));
    const group = L.layerGroup(
      airports.map((a) => {
        const radius = 6 + 14 * Math.sqrt(a.inbound_passengers / maxPax);
        return L.circleMarker([a.lat, a.lon], {
          radius, color: "#1A2744", weight: 1.5, fillColor: "#2E86DE", fillOpacity: 0.65,
        }).bindTooltip(
          `<strong>${a.name} (${a.iata})</strong><br/>` +
          `${Math.round(a.inbound_passengers).toLocaleString()} inbound intl. passengers` +
          `<br/><span style="color:#888">month of ${a.period_start}</span>`,
          { sticky: true },
        );
      }),
    );
    group.addTo(map);
    airportLayerRef.current = group;
  }, [airports, viewMode]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}
