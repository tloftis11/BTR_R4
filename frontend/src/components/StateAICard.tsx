import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

interface Props {
  state: string;
}

/** Auto-loads on state selection. Short, cheap (haiku), cached 1h server-side
 * -- distinct from BriefingModal, which is deliberately triggered and longer.
 */
export function StateAICard({ state }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["state-card", state],
    queryFn: () => api.stateCard(state),
    staleTime: 60 * 60 * 1000,
  });

  return (
    <div style={{
      margin: "0 0 12px", padding: "10px 12px", borderRadius: 8,
      background: "#EBF2FB", border: "1px solid #cfe0f5",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 13 }}>🤖</span>
        <span style={{
          fontSize: 11, fontWeight: 700, color: "#1A2744",
          textTransform: "uppercase", letterSpacing: "0.04em",
        }}>
          AI Analyst
        </span>
      </div>
      {isLoading && <div style={{ fontSize: 12, color: "#7A92AB" }}>Analyzing {state}…</div>}
      {isError && <div style={{ fontSize: 12, color: "#C22828" }}>Couldn't generate analysis.</div>}
      {data && <div style={{ fontSize: 12.5, color: "#222", lineHeight: 1.5 }}>{data.content}</div>}
    </div>
  );
}
