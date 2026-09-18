import type { StateSignals, Pathogen } from "../types";

const PATHOGENS: Pathogen[] = ["SARS-CoV-2", "Influenza A", "RSV"];
const WASTEWATER_CATEGORIES = ["Very Low", "Low", "Moderate", "High", "Very High"];
const TREND_ARROW: Record<string, string> = { rising: "↑", falling: "↓", stable: "→" };
const TREND_COLOR: Record<string, string> = { rising: "#C22828", falling: "#1E8A4C", stable: "#7A92AB" };

interface Props {
  stateName: string;
  signals: StateSignals | undefined;
}

/** The structured (non-AI) trend data for a selected state -- all 3
 * pathogens side by side, not just whichever is on the map toggle. Visible
 * without waiting on an AI call; the AI card (StateAICard) sits above this
 * and synthesizes across it.
 */
export function StateDetailPanel({ stateName, signals }: Props) {
  return (
    <div>
      <h3 style={{ margin: "0 0 10px", fontSize: 14, color: "#1A2744" }}>{stateName}</h3>

      <Section title="Wastewater">
        {PATHOGENS.map((p) => {
          const w = signals?.wastewater[p];
          if (!w) return <NoData key={p} pathogen={p} />;
          return (
            <div key={p} style={{ marginBottom: 6 }}>
              <PathogenLabel pathogen={p} trend={w.trend} />
              <div style={{ fontSize: 11, color: "#555", marginLeft: 2 }}>
                {WASTEWATER_CATEGORIES
                  .filter((c) => w.category_distribution[c])
                  .map((c) => `${c} ×${w.category_distribution[c]}`)
                  .join("  ")}
                <span style={{ color: "#aaa" }}> ({w.site_count} sites)</span>
              </div>
            </div>
          );
        })}
      </Section>

      <Section title="Syndromic (% ED visits)">
        {PATHOGENS.map((p) => {
          const s = signals?.syndromic[p];
          if (!s) return <NoData key={p} pathogen={p} />;
          return (
            <div key={p} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: "#333" }}>{p}: <strong>{s.percent_ed_visits}%</strong></span>
              {s.trend && <span style={{ fontSize: 11, color: "#7A92AB" }}>{s.trend}</span>}
            </div>
          );
        })}
      </Section>

      <Section title="Genomic (SARS-CoV-2 only)">
        {signals?.genomic ? (
          <div style={{ fontSize: 12, color: "#333" }}>
            <div>Leading variant: <strong>{signals.genomic.current_leader.variant}</strong> ({(signals.genomic.current_leader.share * 100).toFixed(0)}%)</div>
            {signals.genomic.fastest_growing && (
              <div style={{ color: "#C22828", marginTop: 2 }}>
                {"↑"} Fastest growing: <strong>{signals.genomic.fastest_growing.variant}</strong>{" "}
                (+{(signals.genomic.fastest_growing.change! * 100).toFixed(0)} pts)
              </div>
            )}
            <div style={{ fontSize: 10, color: "#aaa", marginTop: 4 }}>
              CDC's Variant Proportions source doesn't track other pathogens' lineages.
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: "#aaa" }}>No data</div>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14, paddingBottom: 12, borderBottom: "1px solid #eef1f6" }}>
      <div style={{
        fontSize: 10, fontWeight: 700, color: "#7A92AB",
        textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function PathogenLabel({ pathogen, trend }: { pathogen: Pathogen; trend: string }) {
  return (
    <span style={{ fontSize: 12, color: "#333" }}>
      <strong>{pathogen}</strong>{" "}
      <span style={{ color: TREND_COLOR[trend] ?? "#7A92AB", fontWeight: 700 }}>
        {TREND_ARROW[trend] ?? ""} {trend}
      </span>
    </span>
  );
}

function NoData({ pathogen }: { pathogen: Pathogen }) {
  return <div style={{ fontSize: 12, color: "#bbb", marginBottom: 6 }}>{pathogen}: no data</div>;
}
