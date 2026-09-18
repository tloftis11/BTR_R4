import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { StatesResponse, Airport, Domain, DomainSignal } from "../types";

const NO_DATA_STYLE: L.PathOptions = {
  color: "#b0bec5", weight: 0.5, fillColor: "#eceff1", fillOpacity: 0.4,
};

const DOMAIN_LABEL: Record<Domain, string> = {
  wastewater: "Wastewater (WVAL)",
  syndromic: "Syndromic (% ED visits)",
  genomic: "Genomic (dominant variant share)",
};

// Light-yellow -> dark-red ramp, position 0-1 within the observed range for
// whichever domain is currently selected (ranges differ wildly by domain --
// wval can spike into the hundreds, percent_ed_visits is usually <5,
// variant share is a 0-1 proportion -- so a fixed scale would misrepresent
// most of them).
function rampColor(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const stops: [number, string][] = [
    [0, "#ffffcc"], [0.25, "#fed976"], [0.5, "#fd8d3c"], [0.75, "#e31a1c"], [1, "#800026"],
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (clamped >= t0 && clamped <= t1) {
      const localT = (clamped - t0) / (t1 - t0);
      return lerpColor(c0, c1, localT);
    }
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

interface Props {
  geojson: GeoJSON.FeatureCollection | undefined;
  statesData: StatesResponse | undefined;
  airports: Airport[];
  domain: Domain;
  selectedState: string | null;
  onSelectState: (name: string) => void;
}

export function BiothreatMap({ geojson, statesData, airports, domain, selectedState, onSelectState }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const stateLayerRef = useRef<L.GeoJSON | null>(null);
  const airportLayerRef = useRef<L.LayerGroup | null>(null);
  const selectedRef = useRef<string | null>(selectedState);

  useEffect(() => { selectedRef.current = selectedState; }, [selectedState]);

  // Init map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current, {
      center: [39.5, -98.5],
      zoom: 4,
      zoomSnap: 0.5,
    });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      opacity: 0.35,
    }).addTo(mapRef.current);
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // (Re)build the state choropleth whenever the geojson, data, or domain changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !geojson) return;

    if (stateLayerRef.current) {
      map.removeLayer(stateLayerRef.current);
      stateLayerRef.current = null;
    }

    const values: number[] = [];
    if (statesData) {
      for (const s of Object.values(statesData.states)) {
        const sig = s[domain] as DomainSignal | undefined;
        if (sig) values.push(sig.value);
      }
    }
    const min = values.length ? Math.min(...values) : 0;
    const max = values.length ? Math.max(...values) : 1;
    const range = max - min || 1;

    stateLayerRef.current = L.geoJSON(geojson, {
      style: (feature) => {
        const name = feature?.properties?.name as string | undefined;
        const sig = name ? statesData?.states[name]?.[domain] : undefined;
        if (!sig) return NO_DATA_STYLE;
        return {
          color: "#fff",
          weight: name === selectedRef.current ? 2.5 : 0.8,
          fillColor: rampColor((sig.value - min) / range),
          fillOpacity: 0.8,
        };
      },
      onEachFeature: (feature, layer) => {
        const name = feature.properties?.name as string | undefined;
        const sig = name ? statesData?.states[name]?.[domain] : undefined;
        const label = name
          ? sig
            ? `<strong>${name}</strong><br/>${DOMAIN_LABEL[domain]}: <strong>${sig.value.toFixed(3)}</strong>` +
              `<br/><span style="color:#888">as of ${sig.period_end} (${sig.granularity})</span>`
            : `<strong>${name}</strong><br/>No data for this domain`
          : "";
        layer.bindTooltip(label, { sticky: true, opacity: 0.95 });
        layer.on("click", () => name && onSelectState(name));
        layer.on("mouseover", function () {
          (this as L.Path).setStyle({ weight: 2, color: "#1A2744" });
        });
        layer.on("mouseout", function () {
          stateLayerRef.current?.resetStyle(this as L.Path);
        });
      },
    }).addTo(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geojson, statesData, domain]);

  // Airport markers, sized by inbound passenger volume. Independent layer,
  // rebuilt only when the airport list changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !airports.length) return;

    if (airportLayerRef.current) {
      map.removeLayer(airportLayerRef.current);
    }
    const maxPax = Math.max(...airports.map((a) => a.inbound_passengers));
    const group = L.layerGroup(
      airports.map((a) => {
        const radius = 6 + 14 * Math.sqrt(a.inbound_passengers / maxPax);
        return L.circleMarker([a.lat, a.lon], {
          radius,
          color: "#1A2744",
          weight: 1.5,
          fillColor: "#2E86DE",
          fillOpacity: 0.65,
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
  }, [airports]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}
