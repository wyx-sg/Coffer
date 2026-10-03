// src/lib/hooks/useClis.ts — TanStack Query bindings for the command-line tools (/clis): required by skills or MCP servers, or added by hand.
//
// Reads: the list (problems first), one tool, a preview of a typed name for the
// Add dialog, and the interface kept for a tool (never runs it). Writes: Check
// again (re-probes every tool and writes the answer into the cache), add / edit
// / remove a tool declared by hand, and read the interface (runs only the
// tool's `--help`). Coffer never installs a command: fixing one is handed to an
// agent (`Cli.handoff`). The sidebar's attention signal is derived from the
// same list query the page reads.
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { clisApi, type CliAddInput, type CliEditInput } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliInterfaceKey, cliKey, cliPreviewKey, clisKey } from "@/lib/api/queryKeys";

export function useClis() {
  return useQuery({ queryKey: clisKey, queryFn: () => clisApi.list() });
}

export function useCli(command: string) {
  return useQuery({
    queryKey: cliKey(command),
    queryFn: () => clisApi.get(command),
    enabled: !!command,
  });
}

/** What Coffer finds for `command` (a name or absolute path) — the Add dialog's
 *  "found it / not found" line. Probes the version, nothing else. */
export function useCliPreview(command: string) {
  return useQuery({
    queryKey: cliPreviewKey(command),
    queryFn: () => clisApi.preview(command),
    enabled: command.trim() !== "",
    staleTime: 0,
    retry: false,
  });
}

/** The interface kept for the tool as it is now. A GET never runs the tool:
 *  `not_read` until {@link useReadCliInterface} has run its help. */
function useCliInterface(command: string, enabled = true) {
  return useQuery({
    queryKey: cliInterfaceKey(command),
    queryFn: () => clisApi.interface(command),
    enabled: enabled && !!command,
  });
}

/** The interface of a tool, read by itself the first time it is wanted: what
 *  the daemon kept shows at once, and when nothing is kept for this version the
 *  tool's help is run once (a failure is left to the caller: `read.error`;
 *  `read.mutate()` tries again). `enabled` is false for a tool that is not on
 *  this machine. */
export function useCliInterfaceAuto(command: string, enabled: boolean) {
  const query = useCliInterface(command, enabled);
  const read = useReadCliInterface(command);
  const asked = useRef<string | null>(null);
  const status = query.data?.status;
  const { mutate } = read;
  useEffect(() => {
    if (enabled && status === "not_read" && asked.current !== command) {
      asked.current = command;
      mutate();
    }
  }, [enabled, status, command, mutate]);
  return { query, read };
}

function useToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

/** Check again for every command: the answer replaces the list. */
export function useCheckClis() {
  const qc = useQueryClient();
  const onError = useToastError();
  return useMutation({
    mutationFn: () => clisApi.checkAll(),
    onSuccess: (list) => {
      qc.setQueryData(clisKey, list);
      // The per-command details were probed too.
      void qc.invalidateQueries({ queryKey: clisKey, predicate: (q) => q.queryKey.length > 1 });
    },
    onError,
  });
}

/** Run the tool's help and keep the tree: the answer replaces the cached one.
 *  A failure is shown by the Commands tab itself, so it carries no toast. */
function useReadCliInterface(command: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => clisApi.readInterface(command),
    onSuccess: (tree) => qc.setQueryData(cliInterfaceKey(command), tree),
  });
}

/** Add a tool by hand. The Add dialog shows a failure inline, so no toast. */
export function useAddCli() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CliAddInput) => clisApi.add(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: clisKey }),
  });
}

/** Edit a tool added by hand. The dialog shows a failure inline, so no toast. */
export function useEditCli(command: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CliEditInput) => clisApi.edit(command, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: clisKey }),
  });
}

/** Remove a hand-added declaration; a skill that requires the tool keeps it
 *  listed, so the detail is refetched rather than dropped. */
export function useRemoveCli() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (command: string) => clisApi.remove(command),
    onSuccess: () => void qc.invalidateQueries({ queryKey: clisKey }),
  });
}
