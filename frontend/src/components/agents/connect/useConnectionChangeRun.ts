// src/components/agents/connect/useConnectionChangeRun.ts — applies a reviewed connection change, one agent at a time.
//
// Nothing is written before Apply. Each agent's steps run in sequence — Add
// registers the agent (the daemon creates a never-run agent's directory) and
// then connects it; Connect / Repair installs the missing parts; Disconnect
// removes Coffer's parts — and the agent's items move applying → applied, or
// fail together with the translated error when its call fails. A retry
// re-runs only the failed agents, and a registration that already succeeded
// is not repeated.
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { ChangeStatus } from "@/components/change-preview/changeCounts";
import { agentsApi, type AgentType, type AgentTypeOut } from "@/lib/api/agents";
import { clearConnectFailure, recordConnectFailure } from "@/lib/agents/connectFailure";
import { translateApiError } from "@/lib/api/errors";
import { agentsKey } from "@/lib/api/queryKeys";
import { useAgentConnect, useRegisterAgent } from "@/lib/hooks/useAgents";

export type ChangeKind = "add" | "connect" | "disconnect";

export interface AgentProgress {
  status: ChangeStatus;
  error?: string;
}

export type RunPhase = "review" | "applying" | "done";

export function useConnectionChangeRun(kind: ChangeKind | undefined, connectUid: string) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const register = useRegisterAgent();
  const connection = useAgentConnect(connectUid);
  const [phase, setPhase] = useState<RunPhase>("review");
  const [progress, setProgress] = useState<Partial<Record<AgentType, AgentProgress>>>({});
  // Uids assigned during this run, so a retry does not register twice.
  const assigned = useRef<Partial<Record<AgentType, string>>>({});

  const mark = (type: AgentType, next: AgentProgress) =>
    setProgress((prev) => ({ ...prev, [type]: next }));

  const step = async (row: AgentTypeOut): Promise<void> => {
    if (kind === "add") {
      let uid = assigned.current[row.type] ?? row.uid ?? null;
      if (!uid) {
        uid = (await register.mutateAsync({ type: row.type })).uid;
        assigned.current[row.type] = uid;
      }
      await agentsApi.connect(uid);
      return;
    }
    await connection.mutateAsync(kind === "connect");
  };

  const run = async (rows: readonly AgentTypeOut[]) => {
    setPhase("applying");
    setProgress((prev) => {
      const next = { ...prev };
      for (const row of rows) next[row.type] = { status: "pending" };
      return next;
    });
    for (const row of rows) {
      mark(row.type, { status: "applying" });
      const uidOf = () =>
        (kind === "add" ? (assigned.current[row.type] ?? row.uid) : connectUid) || null;
      try {
        await step(row);
        mark(row.type, { status: "applied" });
        const uid = uidOf();
        if (uid) clearConnectFailure(uid);
      } catch (error) {
        const reason = translateApiError(t, error);
        mark(row.type, { status: "failed", error: reason });
        // The Overview keeps saying why a Connect failed after the dialog closes.
        const uid = uidOf();
        if (uid && kind !== "disconnect") recordConnectFailure(uid, reason);
      }
    }
    // One prefix covers the types, list and detail reads and every agent's
    // connection and hooks under it.
    void qc.invalidateQueries({ queryKey: agentsKey });
    setPhase("done");
  };

  const reset = () => {
    setPhase("review");
    setProgress({});
    assigned.current = {};
  };

  return { phase, progress, run, reset };
}
