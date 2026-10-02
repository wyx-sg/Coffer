// src/lib/hooks/useShellUpdates.ts — the desktop shell's update record, live.
//
// Not a TanStack query: the record is the shell's, not the daemon's, and it
// changes by itself (a timer check, download progress). The hook reads it once
// and then follows the shell's `coffer://update` announcements; the actions
// hand back the record the shell left, so the page never guesses a phase.
import { useCallback, useEffect, useState } from "react";

import {
  checkForUpdates,
  getUpdateStatus,
  installUpdate,
  onUpdateStatus,
  saveAutoCheckPreference,
  setUpdateAutoCheck,
  updatesAvailable,
  type UpdateStatus,
} from "@/lib/shellUpdates";

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export interface ShellUpdates {
  /** False in a browser, which offers no update control. */
  inShell: boolean;
  /** The shell's record; null until it has answered. */
  status: UpdateStatus | null;
  /** Why the last action could not start, when the shell refused it. */
  actionError: string | null;
  check: () => Promise<void>;
  install: () => Promise<void>;
  setAutoCheck: (enabled: boolean) => Promise<void>;
}

export function useShellUpdates(): ShellUpdates {
  const inShell = updatesAvailable();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!inShell) return;
    let live = true;
    // The first read must not overwrite a record that is newer than it: an
    // announcement (or an action's answer) that lands before the read does is
    // the later word.
    getUpdateStatus()
      .then((s) => live && setStatus((current) => current ?? s))
      .catch((e: unknown) => live && setActionError(message(e)));
    const stop = onUpdateStatus((s) => live && setStatus(s));
    return () => {
      live = false;
      stop();
    };
  }, [inShell]);

  const check = useCallback(async () => {
    setActionError(null);
    try {
      setStatus(await checkForUpdates());
    } catch (e) {
      setActionError(message(e));
    }
  }, []);

  const install = useCallback(async () => {
    setActionError(null);
    try {
      // On success the app relaunches and this never settles.
      await installUpdate();
    } catch (e) {
      setActionError(message(e));
      getUpdateStatus()
        .then(setStatus)
        .catch(() => {});
    }
  }, []);

  const setAutoCheck = useCallback(async (enabled: boolean) => {
    saveAutoCheckPreference(enabled);
    try {
      setStatus(await setUpdateAutoCheck(enabled));
    } catch (e) {
      setActionError(message(e));
    }
  }, []);

  return { inShell, status, actionError, check, install, setAutoCheck };
}
