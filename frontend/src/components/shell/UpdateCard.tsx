// src/components/shell/UpdateCard.tsx — the dismissible "update ready" card above the sidebar footer.
//
// Board 1.2.07 and the behaviour sheet (1.2.20, "Updates"): the desktop shell
// checks at launch and every few hours; when a newer version is on offer a
// card above the footer names it with Restart and What's new. Restart asks the
// shell to download, verify and install it, then relaunch; a refusal (a bad
// signature, a failed download) stays on the card with the reason. It is never a
// modal, and a dismissed card comes back at the next launch — dismissal lives
// in this page's memory only. A browser cannot replace the app, so it shows
// no card (the check, download and relaunch are the shell's: spec desktop-app
// "Check for updates against a signed release manifest").
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useShellUpdates } from "@/lib/hooks/useShellUpdates";
import { useOpenSettings } from "@/lib/settingsModal";

// Module state, not storage: a dismissed card returns at the next launch.
let dismissedVersion: string | null = null;

export function UpdateCard({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  const updates = useShellUpdates();
  const openSettings = useOpenSettings();
  const [, rerender] = useState(0);
  const phase = updates.status?.phase;
  // The card stays through the download and install Restart starts, so the
  // button can say it is working until the app relaunches.
  const installing = phase === "downloading" || phase === "installing";
  const offer = phase === "available" || installing ? (updates.status?.available ?? null) : null;
  if (!updates.inShell || !offer || collapsed || dismissedVersion === offer.version) return null;

  return (
    <section
      aria-label={t("nav.update.title")}
      data-testid="update-card"
      className="mx-0.5 flex shrink-0 flex-col gap-2 rounded-xl border border-border bg-surface-raised p-3"
    >
      <div className="flex items-center gap-2">
        <ArrowUpCircle className="size-[15px] text-accent-text" strokeWidth={1.75} aria-hidden />
        <span className="text-sm font-semibold text-text">{t("nav.update.title")}</span>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label={t("nav.update.dismiss")}
              onClick={() => {
                dismissedVersion = offer.version;
                rerender((n) => n + 1);
              }}
              className="ml-auto inline-flex rounded-xs text-text-subtle hover:text-text"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">{t("nav.update.dismiss")}</TooltipContent>
        </Tooltip>
      </div>
      <p className="text-xs leading-normal text-text-muted">
        <span className="font-mono text-2xs text-text">{`v${offer.version}`}</span>{" "}
        {t("nav.update.body")}
      </p>
      {updates.actionError ? (
        <p className="text-xs leading-normal text-danger">{updates.actionError}</p>
      ) : null}
      <div className="flex gap-1.5">
        <Button size="sm" loading={installing} onClick={() => void updates.install()}>
          {t("nav.update.restart")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => openSettings("about")}>
          {t("nav.update.whatsNew")}
        </Button>
      </div>
    </section>
  );
}
