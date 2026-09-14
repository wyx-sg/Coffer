// frontend/src/kinds/memory/useMemory.ts
//
// ALL queries + mutations for the `memory` kind (agents/frontend.md §3). Keys
// are hierarchical under one `["memory"]` root so a write with cross-cutting
// effects — a sync, an organise pass, any override — can invalidate the whole
// subtree with a prefix, mirroring `kinds/knowledge/useKnowledge.ts`.
//
// Overrides are NOT partition-scoped (one table, keyed by fact key, spec
// memory FR-070), so `useMemoryOverrides` fetches the whole list once; callers
// that need "does fact X have a developer decision" build a lookup from it
// rather than each fact paying its own GET.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  clearOverrideField,
  getFact,
  installDelivery,
  listDelivery,
  listFacts,
  listOverrides,
  listPartitions,
  organise,
  patchOverride,
  removeDelivery,
  sync,
} from "./api";
import type { OverrideField, OverridePatch } from "./types";

export const memoryKey = ["memory"] as const;
export const partitionsKey = () => [...memoryKey, "partitions"] as const;
export const factsKey = (partition: string) => [...memoryKey, "facts", partition] as const;
export const factKey = (partition: string, slug: string) =>
  [...memoryKey, "facts", partition, slug] as const;
export const overridesKey = () => [...memoryKey, "overrides"] as const;
export const deliveryKey = () => [...memoryKey, "delivery"] as const;

/** Every lifecycle act that can change what a fact's overrides say
 * (hide/pin/supersede/settle) invalidates broadly: the developer's decision
 * can touch two facts at once (a settled conflict resolves both sides, FR-041
 * / `overrides.py`'s `_settle_conflict`) and nothing here is worth threading a
 * narrower key for. */
function invalidateMemory(qc: ReturnType<typeof useQueryClient>): void {
  void qc.invalidateQueries({ queryKey: memoryKey });
}

export function useMemoryPartitions() {
  return useQuery({
    queryKey: partitionsKey(),
    queryFn: async () => (await listPartitions()).partitions,
  });
}

export function useMemoryFacts(partition: string, enabled = true) {
  return useQuery({
    queryKey: factsKey(partition),
    queryFn: async () => (await listFacts(partition)).facts,
    enabled: enabled && partition.length > 0,
  });
}

/** One fact's body + origins, fetched lazily — a partition holds hundreds of
 * facts (spec memory §Assumptions), so this is fetched per-fact on demand
 * (e.g. "show origins"), never eagerly for a whole list. */
export function useMemoryFact(partition: string, slug: string | null) {
  return useQuery({
    queryKey: factKey(partition, slug ?? ""),
    queryFn: () => getFact(partition, slug as string),
    enabled: Boolean(partition && slug),
  });
}

/** The developer's decisions across every fact (FR-040), one query for the
 * whole table. */
export function useMemoryOverrides() {
  return useQuery({
    queryKey: overridesKey(),
    queryFn: async () => (await listOverrides()).overrides,
  });
}

/** Read the agents' native memory now. Partitions, fact counts and the whole
 * facts subtree can all change, so the invalidation is the full `["memory"]`
 * prefix — same breadth as knowledge's tidy. */
export function useSyncMemory() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: sync,
    onSuccess: (result) => {
      invalidateMemory(qc);
      toast.success(
        t("memory.syncDone", {
          count: result.facts_written,
          partitions: result.partitions.length,
        }),
      );
      if (result.failures.length > 0) {
        toast.error(t("memory.syncFailures", { count: result.failures.length }));
      }
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Merge duplicates, propose supersessions/conflicts and rewrite one
 * partition's digest. */
export function useOrganisePartition(partition: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => organise(partition),
    onSuccess: () => {
      invalidateMemory(qc);
      toast.success(t("memory.detail.organiseDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Apply one or more of the four overrides to a fact (hide, pin, supersede,
 * settle) — a partial patch, so setting one never disturbs another already
 * recorded on the same fact. */
export function useSetOverride() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (vars: { factKey: string; patch: OverridePatch }) =>
      patchOverride(vars.factKey, vars.patch),
    onSuccess: () => invalidateMemory(qc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Clear one override field back to "no decision", e.g. un-hide or un-pin. */
export function useClearOverride() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (vars: { factKey: string; field: OverrideField }) =>
      clearOverrideField(vars.factKey, vars.field),
    onSuccess: () => invalidateMemory(qc),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Per-agent delivery state — whether installed, and when it last actually
 * fired (FR-055). Omit `agent` to list every agent delivery can install for. */
export function useMemoryDelivery(agent?: string) {
  return useQuery({
    queryKey: agent ? [...deliveryKey(), agent] : deliveryKey(),
    queryFn: async () => (await listDelivery(agent)).delivery,
  });
}

export function useInstallDelivery() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agent: string) => installDelivery(agent),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: deliveryKey() });
      toast.success(t("memory.delivery.installDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/** Removal only takes out Coffer's own marker-scoped entry — nothing else in
 * the agent's own settings file is touched (spec memory FR-054). */
export function useRemoveDelivery() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (agent: string) => removeDelivery(agent),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: deliveryKey() });
      toast.success(t("memory.delivery.removeDone"));
    },
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
