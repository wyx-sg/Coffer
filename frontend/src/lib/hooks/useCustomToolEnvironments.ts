// src/lib/hooks/useCustomToolEnvironments.ts — a custom-tool group's environments: add or change one, its
// switch, and delete. Each write answers with the whole group, settled into the cache like a tool write.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import {
  customToolsApi,
  type CustomToolGroup,
  type CustomToolEnvironmentIn,
  type CustomToolEnvironmentPatch,
} from "@/lib/api/customTools";
import { translateApiError } from "@/lib/api/errors";
import { settle, useApprovalNotice } from "./useCustomTools";

/** Add an environment, or change one (`name` set): the dialog renders a failure inline. */
export function useSaveCustomToolEnvironment(group: string) {
  const qc = useQueryClient();
  const notice = useApprovalNotice();
  return useMutation({
    mutationFn: ({
      name,
      body,
    }: {
      name: string | null;
      body: CustomToolEnvironmentIn | CustomToolEnvironmentPatch;
    }) =>
      name === null
        ? customToolsApi.addEnvironment(group, body as CustomToolEnvironmentIn)
        : customToolsApi.updateEnvironment(group, name, body as CustomToolEnvironmentPatch),
    meta: { secretDestination: (next: unknown) => (next as CustomToolGroup).uid },
    onSuccess: (next) => {
      settle(qc, next);
      notice(next);
    },
  });
}

/** An environment's switch, from its row: a failure toasts. */
export function useToggleCustomToolEnvironment(group: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      customToolsApi.updateEnvironment(group, name, { enabled }),
    onSuccess: (next) => settle(qc, next),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** The ConfirmDialog renders a failed delete inline. */
export function useDeleteCustomToolEnvironment(group: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => customToolsApi.removeEnvironment(group, name),
    onSuccess: (next) => settle(qc, next),
  });
}
