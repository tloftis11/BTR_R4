import type { DataSource } from "../types";

interface Props {
  sources: DataSource[] | undefined;
  isLoading: boolean;
}

const ACCESS_COLOR: Record<string, string> = {
  open_api: "#1E8A4C",
  open_scrape: "#C9920C",
  restricted: "#C22828",
  discontinued: "#9AA5B1",
};

export function SourcesPanel({ sources, isLoading }: Props) {
  return (
    <div style={{ padding: 16, overflowY: "auto", height: "100%" }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 13, color: "#1A2744", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Data Sources
      </h3>
      <p style={{ margin: "0 0 14px", fontSize: 11, color: "#7A92AB" }}>
        Every source evaluated for this project, including ones deliberately excluded.
      </p>
      {isLoading && <div style={{ fontSize: 12, color: "#7A92AB" }}>Loading…</div>}
      {sources?.map((s) => (
        <div key={s.name} style={{ borderBottom: "1px solid #e8eef6", padding: "10px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontWeight: 700, fontSize: 12, color: "#1A2744" }}>{s.name}</span>
            <span style={{
              fontSize: 9, fontWeight: 700, color: "#fff", padding: "2px 6px", borderRadius: 3,
              background: ACCESS_COLOR[s.access_model] ?? "#9AA5B1", whiteSpace: "nowrap",
            }}>
              {s.access_model.replace("_", " ")}
            </span>
          </div>
          <div style={{ fontSize: 11, color: "#7A92AB", margin: "2px 0" }}>
            {s.sponsor} &middot; {s.domain} &middot; {s.cadence}
          </div>
          <div style={{ fontSize: 11, color: "#444", lineHeight: 1.4 }}>{s.notes}</div>
        </div>
      ))}
    </div>
  );
}
