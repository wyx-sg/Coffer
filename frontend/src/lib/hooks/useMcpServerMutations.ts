// frontend/src/lib/hooks/useMcpServerMutations.ts — the MCP-server-specific
// writes (edit, add from the paste box / form / review, test connection).
// Enable/disable/delete are kind-agnostic and live in useResourceMutations.ts.
//
// None of these toast on error: each caller renders the failure inline where
// the user acted (the edit dialog's alert, the import dialog's callout, the
// detail page's test-failure banner), and a toast would repeat the same text.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { mcpServersApi, type McpTestResult } from "@/lib/api/mcpServers";
import { mcpStatusKey, pendingApprovalsKey, resourcesKey } from "@/lib/api/queryKeys";
import { saveMcpServerEdit, type SaveArgs } from "@/lib/mcp/editMcpServerSave";
import { importMcpServers, type ImportMcpServersArgs } from "@/lib/mcp/importMcpServers";

/** Save the edit dialog: rotate secrets, then PATCH the resource. The
 *  caller closes the dialog via `mutate(args, { onSuccess })`. */
export function useSaveMcpServerEdit() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (args: Omit<SaveArgs, "t">) => saveMcpServerEdit({ ...args, t }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      // A changed command or URL waits for approval from the save on.
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    },
  });
}

/**
 * Add servers from the Add server dialog (one from the form, several from the
 * review). `created` carries what this dialog session already registered so a
 * retry re-attempts only the failures. Resolves with a report — it never
 * rejects, since a partial batch is an outcome the dialog renders, not an
 * error. The resources cache is refreshed whether or not every server made it.
 */
export function useImportMcpServers() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  return useMutation({
    mutationFn: (vars: Omit<ImportMcpServersArgs, "t">) => importMcpServers({ ...vars, t }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: resourcesKey });
      // A server registered with a secret already in use waits for approval
      // from the registration on.
      void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    },
  });
}

const runMcpServerTest = (uid: string): Promise<McpTestResult> => mcpServersApi.test(uid);

/**
 * Test servers just added, once each, and refresh what their result changes
 * (status + list). Returns the test of every uid, settled — the caller toasts
 * a one-server result and ignores a batch's (fire and forget; a failing one
 * shows under Needs attention).
 */
export function useTestAddedServers() {
  const qc = useQueryClient();
  return (uids: string[]) =>
    Promise.allSettled(
      uids.map((uid) =>
        runMcpServerTest(uid).finally(() => {
          void qc.invalidateQueries({ queryKey: mcpStatusKey(uid) });
          void qc.invalidateQueries({ queryKey: resourcesKey });
        }),
      ),
    );
}

/** Spawn/connect the server once and report latency. A transport failure is
 *  thrown as an Error carrying the daemon's message, which the detail page
 *  folds into a failing result. */
export function useTestMcpServer(uid: string) {
  return useMutation({
    mutationFn: (): Promise<McpTestResult> => runMcpServerTest(uid),
  });
}
