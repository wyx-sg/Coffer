// src/lib/hooks/useCustomTools.ts — every query and mutation of the Custom tools page.
//
// Tool writes answer with the whole group, which is written straight into the
// group's cache entry and then refreshed with the list. The writes a form
// sends (create, edit, a tool's save, the test run, the OpenAPI reading)
// render their failure inline where the user acted, so they carry no error
// toast; the one-click writes (a tool's switch, All on / All off, a reach
// override) toast theirs.
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import {
  customToolsApi,
  type CustomToolGroup,
  type CustomToolGroupIn,
  type CustomToolGroupPatch,
  type CustomToolIn,
  type OpenApiReadIn,
} from "@/lib/api/customTools";
import { translateApiError } from "@/lib/api/errors";
import {
  customToolGroupKey,
  customToolsKey,
  pendingApprovalsKey,
  resourcesKey,
} from "@/lib/api/queryKeys";

export function useCustomToolGroups() {
  return useQuery({ queryKey: customToolsKey, queryFn: customToolsApi.list });
}

export function useCustomToolGroup(name: string) {
  return useQuery({
    queryKey: customToolGroupKey(name),
    queryFn: () => customToolsApi.get(name),
    enabled: name.length > 0,
  });
}

/** A write answered with the group: store it, refresh the list and the
 *  resource lists a group also appears in. */
function settle(qc: QueryClient, group: CustomToolGroup): void {
  qc.setQueryData(customToolGroupKey(group.name), group);
  void qc.invalidateQueries({ queryKey: customToolsKey });
  void qc.invalidateQueries({ queryKey: resourcesKey });
}

/** Saved, but the bound secret waits for a person in the Coffer app: say so,
 *  since the dialog that saved it just closes. */
function useApprovalNotice() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return (group: CustomToolGroup) => {
    if (group.secret_state !== "pending_approval") return;
    void qc.invalidateQueries({ queryKey: pendingApprovalsKey });
    toast.info(t("customTools.pendingApprovalSaved"));
  };
}

export function useCreateCustomToolGroup() {
  const qc = useQueryClient();
  const notice = useApprovalNotice();
  return useMutation({
    mutationFn: (body: CustomToolGroupIn) => customToolsApi.create(body),
    onSuccess: (group) => {
      settle(qc, group);
      notice(group);
    },
  });
}

export function useUpdateCustomToolGroup(name: string) {
  const qc = useQueryClient();
  const notice = useApprovalNotice();
  return useMutation({
    mutationFn: (body: CustomToolGroupPatch) => customToolsApi.update(name, body),
    onSuccess: (group) => {
      settle(qc, group);
      notice(group);
    },
  });
}

/** The ConfirmDialog renders a failed delete inline. */
export function useDeleteCustomToolGroup(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => customToolsApi.remove(name),
    onSuccess: () => {
      qc.removeQueries({ queryKey: customToolGroupKey(name) });
      void qc.invalidateQueries({ queryKey: customToolsKey });
      void qc.invalidateQueries({ queryKey: resourcesKey });
    },
  });
}

/** What the drawer's Save sends: a new tool (`tool: null`) or a change to one,
 *  and the reach override when it changed. */
interface ToolSave {
  /** The saved tool's current name; `null` adds a new one. */
  tool: string | null;
  /** The whole tool; on a change every editable field is sent, and a `null`
   *  flag goes back to following the method. */
  body: CustomToolIn;
  /** The override to write after the tool (`undefined` = unchanged). */
  reach?: string[] | null;
}

/** The drawer's Save — the tool, then its reach override under the name it
 *  saved as. Rendered inline there. */
export function useSaveCustomTool(group: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ tool, body, reach }: ToolSave) => {
      let saved =
        tool === null
          ? await customToolsApi.addTool(group, body)
          : await customToolsApi.updateTool(group, tool, body);
      if (reach !== undefined) saved = await customToolsApi.setToolReach(group, body.name, reach);
      return saved;
    },
    onSuccess: (next) => settle(qc, next),
    // A tool may have saved before its reach failed: show what is stored.
    onError: () => void qc.invalidateQueries({ queryKey: customToolGroupKey(group) }),
  });
}

/** One tool's switch, from the table. */
export function useToggleCustomTool(group: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ tool, enabled }: { tool: string; enabled: boolean }) =>
      customToolsApi.updateTool(group, tool, { enabled }),
    onSuccess: (next) => settle(qc, next),
    onError: (e) => toast.error(translateApiError(t, e)),
  });
}

/** All on / All off: switch every tool not already in that state. */
export function useSetAllCustomTools(group: string) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast } = useToast();
  return useMutation({
    mutationFn: async ({ tools, enabled }: { tools: string[]; enabled: boolean }) => {
      let last: CustomToolGroup | undefined;
      for (const tool of tools) last = await customToolsApi.updateTool(group, tool, { enabled });
      return last;
    },
    onSuccess: (next) => {
      if (next) settle(qc, next);
    },
    onError: (e) => {
      void qc.invalidateQueries({ queryKey: customToolsKey });
      toast.error(translateApiError(t, e));
    },
  });
}

/** The ConfirmDialog renders a failed delete inline. */
export function useDeleteCustomTool(group: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tool: string) => customToolsApi.removeTool(group, tool),
    onSuccess: (next) => settle(qc, next),
  });
}

/** Run a draft once; the drawer renders the result or the failure. */
export function useTestCustomTool(group: string) {
  return useMutation({
    mutationFn: ({ tool, args }: { tool: CustomToolIn; args: Record<string, unknown> }) =>
      customToolsApi.test(group, tool, args),
  });
}

/** Read a spec; the import step renders the failure under the Spec field. */
export function useReadOpenApi() {
  return useMutation({ mutationFn: (body: OpenApiReadIn) => customToolsApi.readOpenApi(body) });
}

/** Re-import's preview; the dialog renders the failure. */
export function usePreviewReimport(group: string) {
  return useMutation({
    mutationFn: (document?: string) => customToolsApi.previewReimport(group, document),
  });
}

export function useApplyReimport(group: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ add, document }: { add: string[]; document?: string }) =>
      customToolsApi.applyReimport(group, add, document),
    onSuccess: (next) => settle(qc, next),
  });
}
