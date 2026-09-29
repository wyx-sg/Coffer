// frontend/src/lib/hooks/useMcpServerMutations.ts — the MCP-server-specific
// writes (edit, batch import, test connection). Enable/disable/delete are
// kind-agnostic and live in useResourceMutations.ts.
//
// None of these toast on error (a saved edit whose secret waits for approval
// toasts that, since it is not a failure): each caller renders the failure inline where
// the user acted (the edit dialog's alert, the import dialog's callout, the
// detail page's test-failure banner), and a toast would repeat the same text.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getApiClient } from "@/lib/api/client";
import { pendingApprovalsKey, resourcesKey } from "@/lib/api/queryKeys";
import type { components } from "@/lib/api/types";
import { saveMcpServerEdit, type SaveArgs } from "@/components/mcp/editMcpServerSave";
import { importMcpServers, type ImportMcpServersArgs } from "@/components/mcp/importMcpServers";
import { useToast } from "@/components/ui/toast";

type TestResult = components["schemas"]["McpTestResultOut"];

/** Save the edit dialog: rotate credentials, then PATCH the resource. The
 *  caller closes the dialog via `mutate(args, { onSuccess })`. */
export function useSaveMcpServerEdit() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (args: Omit<SaveArgs, "t">) => saveMcpServerEdit({ ...args, t }),
    onSuccess: ({ awaitingApproval }) => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      // Saved, but a replaced secret keeps its old value until someone
      // approves in the Coffer app — say so, since the dialog just closes.
      if (awaitingApproval) {
        void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
        toast.info(t("credentials.savedAwaitingApproval"));
      }
    },
  });
}

/**
 * Import a pasted `mcpServers` batch. `created` carries the names this import
 * session already registered so a retry re-attempts only the failures. The
 * resources cache is refreshed whether or not every server made it — a
 * partial failure still created some.
 */
export function useImportMcpServers() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (vars: Omit<ImportMcpServersArgs, "t">) => importMcpServers({ ...vars, t }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
  });
}

/** Spawn/connect the server once and report latency. A transport failure is
 *  thrown as an Error carrying the daemon's message, which the detail page
 *  folds into a failing result. */
export function useTestMcpServer(uid: string) {
  return useMutation({
    mutationFn: async (): Promise<TestResult> => {
      const client = getApiClient();
      const { data, error } = await client.POST("/resources/mcp_server/{uid}/test", {
        params: { path: { uid } },
      });
      if (error || data === undefined) throw new Error(error?.error?.message ?? "test failed");
      return data;
    },
  });
}
