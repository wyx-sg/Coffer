// frontend/src/lib/hooks/useResourceMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { translateApiError } from "@/lib/api/errors";
import { ownListKeyForKind, resourcesKey } from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import { useToast } from "@/components/ui/toast";

interface EnableDisableInput {
  kind: string;
  name: string;
}

/** A kind-agnostic write refreshes the generic list AND the kind's own list
 *  key, where it has one (`ownListKeyForKind`) — the skill detail page reads
 *  `skillKey(name)`, not `resourcesKey`, and would otherwise keep rendering the
 *  pre-toggle state. */
function invalidateFor(qc: ReturnType<typeof useQueryClient>, kind: string): void {
  void qc.invalidateQueries({ queryKey: resourcesKey });
  const own = ownListKeyForKind(kind);
  if (own) void qc.invalidateQueries({ queryKey: own });
}

export function useEnableResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ kind, name }: EnableDisableInput) => resourcesApi.enable(kind, name),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDisableResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ kind, name }: EnableDisableInput) => resourcesApi.disable(kind, name),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDeleteResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ kind, name }: EnableDisableInput) => resourcesApi.remove(kind, name),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}
