// src/lib/hooks/useClis.ts — TanStack Query bindings for the command-line tools (/clis): required by skills or MCP servers, or added by hand.
//
// Reads: the list (problems first), one tool, and a preview of a typed name for
// the Add dialog. Writes: Check (re-probes every tool, or one, and writes
// the answer into the cache) and add / edit / remove a tool declared by hand. Coffer never installs a command: fixing one is handed to an
// agent (`Cli.handoff`). The sidebar's attention signal is derived from the
// same list query the page reads.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { clisApi, type CliAddInput, type CliEditInput, type CliList } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliKey, cliPreviewKey, clisKey } from "@/lib/api/queryKeys";

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

function useToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

/** Check every command: the answer replaces the list. */
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

/** Check one command: the answer replaces its row in the list. */
export function useCheckCli(command: string) {
  const qc = useQueryClient();
  const onError = useToastError();
  return useMutation({
    mutationFn: () => clisApi.check(command),
    onSuccess: (cli) => {
      qc.setQueryData(cliKey(command), cli);
      qc.setQueryData<CliList>(clisKey, (list) =>
        list ? { ...list, items: list.items.map((c) => (c.command === command ? cli : c)) } : list,
      );
    },
    onError,
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
