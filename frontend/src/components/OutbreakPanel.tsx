import type { OutbreakAlert } from "../types";

interface Props {
  alerts: OutbreakAlert[] | undefined;
  isLoading: boolean;
}

export function OutbreakPanel({ alerts, isLoading }: Props) {
  return (
    <div style={{ padding: 16, overflowY: "auto", height: "100%" }}>
      <h3 style={{ margin: "0 0 4px", fontSize: 13, color: "#1A2744", textTransform: "uppercase", letterSpacing: "0.06em" }}>
        Recent Global Outbreak Alerts
      </h3>
      <p style={{ margin: "0 0 14px", fontSize: 11, color: "#7A92AB" }}>
        WHO Disease Outbreak News — a travel-relevant proxy signal, not a US domestic feed.
      </p>
      {isLoading && <div style={{ fontSize: 12, color: "#7A92AB" }}>Loading…</div>}
      {alerts?.map((a, i) => (
        <div key={i} style={{
          borderBottom: "1px solid #e8eef6", padding: "10px 0",
          fontSize: 12, color: "#333",
        }}>
          <div style={{ fontWeight: 700, color: "#1A2744" }}>{a.country}</div>
          <div style={{ margin: "2px 0" }}>{a.title}</div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#7A92AB", fontSize: 11 }}>
            <span>{a.pathogen ?? "Unspecified pathogen"}</span>
            <span>{a.date}</span>
          </div>
        </div>
      ))}
      {alerts && alerts.length === 0 && (
        <div style={{ fontSize: 12, color: "#7A92AB" }}>No recent alerts in range.</div>
      )}
    </div>
  );
}
