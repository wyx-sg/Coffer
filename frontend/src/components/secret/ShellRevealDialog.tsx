// src/components/secret/ShellRevealDialog.tsx — a value the desktop app revealed for `coffer secret reveal`.
//
// The command only asked; the shell ran the person's presence check itself and hands the value to this window,
// never to the command, the daemon or a log (spec secret "Approve from the command line with the person's own
// presence check"). It shows for 30 seconds with Copy, then is dropped, like the Reveal value dialog.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { onShellEvent } from "@/lib/tauri";

/** The event the shell shows a revealed value on (`desktop_requests.rs`). */
const REVEALED_EVENT = "coffer://revealed";
const SHOW_SECONDS = 30;

interface Revealed {
  ref: string;
  value: string;
}

export function ShellRevealDialog() {
  const { t } = useTranslation();
  const [shown, setShown] = useState<Revealed | null>(null);
  const [left, setLeft] = useState(SHOW_SECONDS);

  useEffect(
    () =>
      onShellEvent<Revealed>(REVEALED_EVENT, (payload) => {
        setShown(payload);
        setLeft(SHOW_SECONDS);
      }),
    [],
  );
  useEffect(() => {
    if (!shown) return;
    if (left <= 0) {
      setShown(null);
      return;
    }
    const timer = window.setTimeout(() => setLeft(left - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [shown, left]);

  return (
    <Dialog open={shown !== null} onOpenChange={(open) => !open && setShown(null)}>
      <DialogContent className="max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("secrets.shellReveal.title", { ref: shown?.ref ?? "" })}</DialogTitle>
          <DialogDescription>{t("secrets.shellReveal.body")}</DialogDescription>
        </DialogHeader>
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-md border border-border-subtle bg-surface-sunken p-3 font-mono text-sm">
          {shown?.value}
        </pre>
        <p className="text-xs text-text-muted">
          {t("secrets.shellReveal.hides", { seconds: left })}
        </p>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => void navigator.clipboard?.writeText(shown?.value ?? "")}
          >
            {t("common.copy")}
          </Button>
          <Button onClick={() => setShown(null)}>{t("common.done")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
