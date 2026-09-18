export interface DomainSignal {
  metric: string;
  value: number;
  period_end: string;
  granularity: string;
}

export interface StateSignals {
  wastewater?: DomainSignal;
  syndromic?: DomainSignal;
  genomic?: DomainSignal;
}

export interface StatesResponse {
  pathogen: string;
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

export type Domain = "wastewater" | "syndromic" | "genomic";
