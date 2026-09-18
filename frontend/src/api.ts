import type {
  StatesResponse, AirportsResponse, AlertsResponse, SourcesResponse,
  StateCardResponse, BriefingResponse,
} from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  mapStates: () => get<StatesResponse>("/api/map/states"),
  mapAirports: () => get<AirportsResponse>("/api/map/airports"),
  outbreakAlerts: (limit = 20) => get<AlertsResponse>(`/api/map/outbreak-alerts?limit=${limit}`),
  sources: () => get<SourcesResponse>("/api/sources"),
  statesGeoJson: () => get<GeoJSON.FeatureCollection>("/api/geojson/states"),
  stateCard: (state: string) =>
    get<StateCardResponse>(`/api/ai/state-card?state=${encodeURIComponent(state)}`),
  briefing: (state?: string, regenerate = false) =>
    get<BriefingResponse>(
      `/api/ai/briefing${state ? `?state=${encodeURIComponent(state)}` : ""}` +
      `${regenerate ? `${state ? "&" : "?"}regenerate=true` : ""}`
    ),
};
