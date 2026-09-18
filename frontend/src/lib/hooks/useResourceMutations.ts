// frontend/src/lib/hooks/useResourceMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { translateApiError } from "@/lib/api/errors";
import { ownListKeyForKind, resourcesKey } from "@/lib/api/queryKeys";
import { resourcesApi } from "@/lib/api/resources";
import { useToast } from "@/components/ui/toast";

/**
 * What every kind-agnostic write needs: the `uid` it acts on, and the `kind` —
 * which is NOT part of the request. The kind is carried purely so `onSuccess`
 * knows which of the per-kind list keys to refresh alongside the generic one;
 * the route itself takes the uid and nothing else.
 */
interface ResourceWriteInput {
  kind: string;
  uid: string;
}

/** A kind-agnostic write refreshes the generic list AND the kind's own list
 *  key, where it has one (`ownListKeyForKind`) — the skill detail page reads
 *  `skillKey(uid)`, not `resourcesKey`, and would otherwise keep rendering the
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
    mutationFn: ({ uid }: ResourceWriteInput) => resourcesApi.enable(uid),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDisableResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ uid }: ResourceWriteInput) => resourcesApi.disable(uid),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

export function useDeleteResource() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ uid }: ResourceWriteInput) => resourcesApi.remove(uid),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
    onError: (error) => toast.error(translateApiError(t, error)),
  });
}

/**
 * Rename a resource of any kind — the same PATCH for all seven, because a name
 * is a label and editing one is an ordinary field edit.
 *
 * No `onError` toast, unlike its siblings: the only way to rename is a form
 * with a name field in it, and the one failure that matters (409, the label is
 * taken) belongs beside that field, where it can be corrected. A toast would
 * say it a second time somewhere the user is not looking.
 */
export function useRenameResource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uid, name }: ResourceWriteInput & { name: string }) =>
      resourcesApi.rename(uid, name),
    onSuccess: (_data, { kind }) => invalidateFor(qc, kind),
  });
}
