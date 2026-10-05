// frontend/src/lib/hooks/useTerminals.ts
// Terminals for the preferred-terminal picker (Settings → General) and the one
// way the web opens an agent session in one (spec daemon "Open an agent session
// in a terminal"). The daemon enumerates what is installed (a browser can't);
// the chosen value stays client-side in localStorage (lib/preferences.ts) and
// travels to the daemon only as the `terminal` of an open, read at click time.
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { fsApi, type OpenTerminalBody, type TerminalOption } from "@/lib/api/fs";
import { fsTerminalsKey } from "@/lib/api/queryKeys";
import { getPreferredTerminal, usePreferredTerminal } from "@/lib/preferences";

/** Reactive list of installed terminals. Empty/failed → the picker shows just
 *  the system terminal and Custom… (detection is best-effort, never blocking). */
export function useDetectedTerminals() {
  return useQuery<TerminalOption[]>({
    queryKey: fsTerminalsKey,
    queryFn: () => fsApi.listTerminals(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** The name of a terminal value: its detected label, "System terminal" for none, "Custom terminal" otherwise. */
function labelOf(
  t: (key: string) => string,
  detected: readonly TerminalOption[],
  terminal: string,
): string {
  if (!terminal) return t("terminal.system");
  return detected.find((d) => d.value === terminal)?.label ?? t("terminal.custom");
}

/** @ui-only What an open falls back to when the daemon refuses: the button of the error toast. */
export interface OpenFallback {
  label: string;
  onClick: () => void;
}

/** What to start: the daemon's `terminal` is filled in from the preference at click time. */
export type OpenRequest = Omit<OpenTerminalBody, "terminal">;

/**
 * Open an agent in the preferred terminal, or in `terminal` when one is named
 * (a one-off pick from a ▾ menu; the preference stays). Resolves true once the
 * daemon has started it (a toast says "Opened in <terminal>"), false when it
 * refused: the toast then carries the translated reason and `fallback` as the
 * way out.
 */
export function useOpenInTerminal() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: detected = [] } = useDetectedTerminals();

  return useCallback(
    async (request: OpenRequest, fallback: OpenFallback, chosen?: string): Promise<boolean> => {
      const terminal = chosen ?? getPreferredTerminal();
      const label = labelOf(t, detected, terminal);
      try {
        await fsApi.openTerminal({ ...request, terminal: terminal || null });
      } catch (error) {
        toast.error(translateApiError(t, error), {
          action: { label: fallback.label, onClick: fallback.onClick },
        });
        return false;
      }
      toast.success(t("terminal.opened", { terminal: label }));
      return true;
    },
    [detected, t, toast],
  );
}

/** The label of the terminal the preference names, for a tooltip ("Start Codex in Terminal …"). */
export function useTerminalLabel(): string {
  const { t } = useTranslation();
  const { data: detected = [] } = useDetectedTerminals();
  return labelOf(t, detected, usePreferredTerminal());
}

/** @ui-only A terminal a ▾ menu offers: its preference value ("" = the system terminal) and name. */
export interface TerminalChoice {
  value: string;
  label: string;
}

/**
 * The preferred terminal's name, and the other terminals on this machine — the
 * system terminal and every detected one — for an "Open in <other>" menu.
 */
export function useTerminalChoices(): { label: string; others: TerminalChoice[] } {
  const { t } = useTranslation();
  const { data: detected = [] } = useDetectedTerminals();
  const preferred = usePreferredTerminal();
  const all: TerminalChoice[] = [
    { value: "", label: t("terminal.system") },
    ...detected.map((d) => ({ value: d.value, label: d.label })),
  ];
  return {
    label: labelOf(t, detected, preferred),
    others: all.filter((c) => c.value !== preferred),
  };
}
