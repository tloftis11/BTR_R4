import type { OutbreakAlert } from "../types";

interface Props {
  alerts: OutbreakAlert[] | undefined;
  isLoading: boolean;
}

/** "Global Biothreat Watch" -- this is the actual emerging-threat signal in
 * the loaded data (WHO Disease Outbreak News: Ebola, Nipah, Hantavirus,
 * Yellow Fever, etc.), not a US domestic feed. Lives in airport-view mode,
 * where travel/global context belongs, rather than as a generic sidebar
 * list shown everywhere.
 */
export function OutbreakPanel({ alerts, isLoading }: Props) {
  return (
    <div style={{ padding: 16, overflowY: "auto", height: "100%" }}>
      <h3 style={{
        margin: "0 0 4px", fontSize: 13, color: "#1A2744",
        textTransform: "uppercase", letterSpacing: "0.06em",
      }}>
        🌐 Global Biothreat Watch
      </h3>
      <p style={{ margin: "0 0 14px", fontSize: 11, color: "#7A92AB" }}>
        WHO Disease Outbreak News — emerging and re-emerging threats worldwide,
        relevant to international travel exposure. Not a US domestic feed.
      </p>
      {isLoading && <div style={{ fontSize: 12, color: "#7A92AB" }}>Loading…</div>}
      {alerts?.map((a, i) => (
        <div key={i} style={{
          borderBottom: "1px solid #e8eef6", padding: "12px 0",
          fontSize: 12, color: "#333",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
            <span style={{ fontWeight: 700, color: "#1A2744" }}>{a.country}</span>
            <span style={{ color: "#7A92AB", fontSize: 11, whiteSpace: "nowrap" }}>{a.date}</span>
          </div>
          <div style={{
            display: "inline-block", fontSize: 10, fontWeight: 700, color: "#fff",
            background: "#C22828", borderRadius: 3, padding: "1px 6px", margin: "4px 0",
          }}>
            {a.pathogen ?? "Unspecified pathogen"}
          </div>
          <div style={{ fontWeight: 600, margin: "4px 0 2px" }}>{a.title}</div>
          {a.excerpt && (
            <div style={{ color: "#555", lineHeight: 1.5, fontSize: 11.5 }}>{a.excerpt}</div>
          )}
        </div>
      ))}
      {alerts && alerts.length === 0 && (
        <div style={{ fontSize: 12, color: "#7A92AB" }}>No recent alerts in range.</div>
      )}
    </div>
  );
}
