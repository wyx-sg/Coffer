// frontend/src/lib/hooks/useResourceMutations.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { translateApiError } from "@/lib/api/errors";
import { resourcesApi } from "@/lib/api/resources";
import { useToast } from "@/components/ui/toast";

interface EnableDisableInput {
  kind: string;
  name: string;
}

/** Some kinds are read through their OWN query key rather than the generic
 *  resource list — `useSkill` reads ["skills", name], `useProvider` reads
 *  ["providers", name]. Invalidating only ["resources"] leaves those surfaces
 *  rendering the pre-toggle state (the skill detail page's activation control
 *  would keep showing "enabled" after a successful disable), so a toggle
 *  refreshes the kind's own key too. */
const KIND_QUERY_KEY: Record<string, string> = {
  skill: "skills",
  provider: "providers",
  agent: "agents",
};

function invalidateFor(qc: ReturnType<typeof useQueryClient>, kind: string): void {
  void qc.invalidateQueries({ queryKey: ["resources"] });
  const own = KIND_QUERY_KEY[kind];
  if (own) void qc.invalidateQueries({ queryKey: [own] });
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
