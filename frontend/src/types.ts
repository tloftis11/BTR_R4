export type Pathogen = "SARS-CoV-2" | "Influenza A" | "RSV";
// Map-colorable domains only. Genomic dropped as a map layer -- HHS-region
// sharing made it too blocky/uninformative spatially -- but genomic data is
// still returned by the API and shown as text in StateDetailPanel + the AI
// endpoints, where it's actually useful (see GenomicSignal below).
export type Domain = "wastewater" | "syndromic";

export interface WastewaterSignal {
  category_distribution: Record<string, number>;
  site_count: number;
  trend: "rising" | "falling" | "stable";
  period_end: string;
}

export interface SyndromicSignal {
  percent_ed_visits: number;
  trend: string | null;
  period_end: string;
}

export interface VariantInfo {
  variant: string;
  share: number;
  change?: number;
}

export interface GenomicSignal {
  current_leader: VariantInfo;
  fastest_growing: VariantInfo | null;
  period_end: string;
}

export interface StateSignals {
  wastewater: Partial<Record<Pathogen, WastewaterSignal>>;
  syndromic: Partial<Record<Pathogen, SyndromicSignal>>;
  genomic: GenomicSignal | null;
}

export interface StatesResponse {
  pathogens: Pathogen[];
  states: Record<string, StateSignals>;
}

export interface Airport {
  iata: string;
  name: string;
  lat: number;
  lon: number;
  inbound_passengers: number;
  period_start: string;
}

export interface AirportsResponse {
  airports: Airport[];
}

export interface OutbreakAlert {
  country: string;
  pathogen: string | null;
  date: string;
  title: string | null;
  excerpt: string | null;
}

export interface AlertsResponse {
  alerts: OutbreakAlert[];
}

export interface DataSource {
  name: string;
  domain: string;
  sponsor: string;
  url: string;
  access_model: string;
  cadence: string;
  notes: string;
}

export interface SourcesResponse {
  sources: DataSource[];
}

export interface StateCardResponse {
  state: string;
  content: string;
  generated_at: string;
  cached: boolean;
}

export interface BriefingResponse {
  scope: string; // state name, or "national"
  content: string;
  generated_at: string;
  cached: boolean;
}
