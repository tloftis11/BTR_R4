import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import type { BriefingResponse } from "../types";

interface Props {
  defaultState: string | null;
  onClose: () => void;
}

/** Deliberately-triggered, longer briefing -- distinct from StateAICard's
 * auto-loading short summary. National or state scope, cached 6h
 * server-side, with a Regenerate action that bypasses the cache.
 */
export function BriefingModal({ defaultState, onClose }: Props) {
  const [scope, setScope] = useState<"national" | "state">(defaultState ? "state" : "national");
  const [regenerating, setRegenerating] = useState(false);
  const queryClient = useQueryClient();

  const stateParam = scope === "state" ? (defaultState ?? undefined) : undefined;
  const queryKey = ["briefing", scope, stateParam ?? "national"];

  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => api.briefing(stateParam, false),
    staleTime: 6 * 60 * 60 * 1000,
  });

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const fresh = await api.briefing(stateParam, true);
      queryClient.setQueryData<BriefingResponse>(queryKey, fresh);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(10,20,40,0.5)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#fff", borderRadius: 12, width: "min(640px, 92vw)",
          maxHeight: "80vh", display: "flex", flexDirection: "column",
          boxShadow: "0 8px 40px rgba(0,0,0,0.3)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{
          padding: "16px 20px", borderBottom: "1px solid #e8eef6",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#1A2744" }}>Biothreat Briefing</div>
          <button
            onClick={onClose}
            style={{ border: "none", background: "none", fontSize: 20, cursor: "pointer", color: "#7A92AB", lineHeight: 1 }}
          >
            &times;
          </button>
        </div>

        <div style={{
          padding: "12px 20px", borderBottom: "1px solid #e8eef6",
          display: "flex", gap: 8, alignItems: "center",
        }}>
          <button
            onClick={() => setScope("national")}
            style={{
              background: scope === "national" ? "#1A2744" : "#f0f3f8",
              color: scope === "national" ? "#fff" : "#333",
              border: "none", borderRadius: 6, padding: "6px 12px",
              fontSize: 12, fontWeight: 700, cursor: "pointer",
            }}
          >
            National
          </button>
          <button
            onClick={() => defaultState && setScope("state")}
            disabled={!defaultState}
            title={defaultState ? undefined : "Select a state on the map first"}
            style={{
              background: scope === "state" ? "#1A2744" : "#f0f3f8",
              color: scope === "state" ? "#fff" : (defaultState ? "#333" : "#bbb"),
              border: "none", borderRadius: 6, padding: "6px 12px",
              fontSize: 12, fontWeight: 700,
              cursor: defaultState ? "pointer" : "default",
            }}
          >
            {defaultState ?? "Select a state"}
          </button>
          <button
            onClick={handleRegenerate}
            disabled={regenerating || isLoading}
            style={{
              marginLeft: "auto", border: "1px solid #cfd8e3", background: "#fff",
              borderRadius: 6, padding: "6px 12px", fontSize: 11,
              cursor: regenerating ? "default" : "pointer", color: "#4A5E78",
            }}
          >
            {regenerating ? "Regenerating…" : "↻ Regenerate"}
          </button>
        </div>

        <div style={{
          padding: 20, overflowY: "auto", fontSize: 13, lineHeight: 1.7,
          color: "#222", whiteSpace: "pre-wrap",
        }}>
          {(isLoading || regenerating) && "Generating briefing…"}
          {isError && <span style={{ color: "#C22828" }}>Couldn't generate briefing.</span>}
          {!isLoading && !regenerating && data?.content}
          {data && !isLoading && !regenerating && (
            <div style={{ marginTop: 16, fontSize: 10, color: "#aaa" }}>
              Generated {new Date(data.generated_at).toLocaleString()} {data.cached ? "(cached)" : ""}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
