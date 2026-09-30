// src/lib/hooks/useClis.ts — TanStack Query bindings for the commands managed skills require (/clis).
//
// Reads: the list (problems first) and one command. Writes: Check again (all,
// or one), which re-probes and writes the fresh answer straight into the cache,
// and the Homebrew install job — started only by the confirmation dialog, then
// followed by polling its output until it ends, after which the daemon has
// re-probed the command and every CLIs query is refreshed. The sidebar's
// attention signal is derived from the same list query the page reads.
import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { clisApi, type CliInstall } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliKey, clisKey } from "@/lib/api/queryKeys";

/** How often a running install's output is asked for. */
const INSTALL_POLL_MS = 1000;

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

/** Check again for one command: the answer replaces its detail, and the list
 *  (which carries the same row) is refreshed. */
export function useCheckCli(command: string) {
  const qc = useQueryClient();
  const onError = useToastError();
  return useMutation({
    mutationFn: () => clisApi.check(command),
    onSuccess: (cli) => {
      qc.setQueryData(cliKey(command), cli);
      void qc.invalidateQueries({ queryKey: clisKey, exact: true });
    },
    onError,
  });
}

/** Whether the sidebar's CLIs entry carries a dot: any required command that
 *  is missing, too old or not logged in — the same rows the attention list
 *  reports as kind `cli`. `false` while loading or after a failed read. */
export function useClisAttention(): boolean {
  const { data } = useClis();
  return (data?.items ?? []).some((cli) => cli.status !== "ready");
}

export interface CliInstallRun {
  /** The job as last reported, `null` before one is started or attached. */
  job: CliInstall | null;
  /** Every output line seen so far, oldest first. */
  lines: string[];
  /** Why starting or following the job failed, shown inline by the dialog. */
  error: unknown;
  starting: boolean;
  /** Run `brew install|upgrade <formula>` — only the dialog's confirm calls it. */
  start: (formula: string) => void;
  /** Follow a job that is already running (opened while one runs). */
  attach: () => void;
}

/**
 * The install job of one command, for the life of the component that asked
 * (the dialog mounts it per opening). No toast on failure: the confirmation
 * dialog renders it inline and stays open (.agents/frontend.md §5).
 */
export function useCliInstall(command: string): CliInstallRun {
  const qc = useQueryClient();
  const [job, setJob] = useState<CliInstall | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);

  const follow = useCallback((next: CliInstall, replace: boolean) => {
    setJob(next);
    setLines((prev) => (replace ? next.lines : [...prev, ...next.lines]));
  }, []);

  const { mutate, isPending } = useMutation({
    mutationFn: (formula: string) => clisApi.install(command, formula),
    onSuccess: (started) => follow(started, true),
    onError: (e) => setError(e),
  });

  // Poll while the job runs, asking only for the lines not seen yet.
  useEffect(() => {
    if (job?.state !== "running") return;
    let live = true;
    const timer = setTimeout(() => {
      clisApi.installStatus(command, job.next_line).then(
        (next) => live && follow(next, false),
        (e: unknown) => live && setError(e),
      );
    }, INSTALL_POLL_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [command, job, follow]);

  // Once it ends the daemon has probed the command again: refresh every view.
  const ended = job !== null && job.state !== "running";
  useEffect(() => {
    if (ended) void qc.invalidateQueries({ queryKey: clisKey });
  }, [ended, qc]);

  return {
    job,
    lines,
    error,
    starting: isPending,
    start: (formula) => {
      setError(null);
      mutate(formula);
    },
    attach: () => {
      clisApi.installStatus(command, 0).then(
        (next) => follow(next, true),
        (e: unknown) => setError(e),
      );
    },
  };
}
