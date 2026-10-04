// frontend/src/pages/settings/SettingsModal.tsx
//
// Settings as a large modal over the page the user is on (spec web-ui "Open
// Settings as a modal from the sidebar footer", "Organise Settings into six
// tabs"). Each tab is a route, `/settings/<tab>`; the shell keeps the page
// underneath rendered, and closing — the close control, Escape, a click
// outside, or browser Back — returns to it at its own route. A tab switch
// replaces the history entry, so Back closes the modal rather than stepping
// through tabs.
//
// The tabs hold the settings pages' existing content (their redesign is later
// work in change revise-web-ui-ia): General with the Speech-to-text section,
// Security, Data, Daemon (with Start at login, moved from General), About and Features.
import { Navigate, useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SETTINGS_TABS, type SettingsTabId } from "@/lib/navigation";
import { useCloseSettings, useOpenSettings } from "@/lib/settingsModal";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import { AboutPage } from "./AboutPage";
import { DaemonSettings } from "./DaemonSettings";
import { DataSettings } from "./DataSettings";
import { ExperimentalFeaturesSettings } from "./ExperimentalFeaturesSettings";
import { GeneralSettings } from "./GeneralSettings";
import { SecuritySettings } from "./SecuritySettings";

const PANES: Record<SettingsTabId, () => JSX.Element | null> = {
  general: GeneralSettings,
  security: SecuritySettings,
  data: DataSettings,
  daemon: DaemonSettings,
  about: AboutPage,
  features: ExperimentalFeaturesSettings,
};

function isTab(value: string | undefined): value is SettingsTabId {
  return SETTINGS_TABS.some((tab) => tab.id === value);
}

export function SettingsModal() {
  const { t } = useTranslation();
  const { tab } = useParams<{ tab: string }>();
  const location = useLocation();
  const openSettings = useOpenSettings();
  const close = useCloseSettings();

  // An unknown tab opens General, over the same page.
  if (!isTab(tab)) return <Navigate to="/settings/general" replace state={location.state} />;
  const Pane = PANES[tab];

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => (open ? undefined : close())}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-dialog bg-scrim data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:duration-base" />
        <DialogPrimitive.Content
          data-testid="settings-modal"
          aria-describedby={undefined}
          className={cn(
            "fixed left-1/2 top-1/2 z-dialog flex h-[min(720px,calc(100vh-2rem))] w-[min(1000px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-surface-raised text-sm text-text shadow-overlay outline-none",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[.98] data-[state=open]:duration-slow data-[state=open]:ease-out",
          )}
        >
          <div className="flex h-[52px] shrink-0 items-center gap-2.5 border-b border-border pl-5 pr-4">
            <DialogPrimitive.Title className="text-md font-bold text-text">
              {t("settings.title")}
            </DialogPrimitive.Title>
            <kbd className="inline-flex h-[18px] items-center rounded-xs border border-border px-1 font-sans text-2xs text-text-subtle">
              {shortcutLabel(",")}
            </kbd>
            <Tooltip>
              <TooltipTrigger asChild>
                <DialogPrimitive.Close
                  aria-label={t("settings.close")}
                  className="ml-auto inline-flex size-7 items-center justify-center rounded-item text-text-muted transition-colors duration-fast hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                >
                  <X className="size-4" aria-hidden />
                </DialogPrimitive.Close>
              </TooltipTrigger>
              <TooltipContent side="bottom" shortcut="Esc">
                {t("settings.close")}
              </TooltipContent>
            </Tooltip>
          </div>
          <div className="flex min-h-0 flex-1 flex-col md:flex-row">
            <nav
              aria-label={t("settings.sections")}
              className="flex shrink-0 gap-px overflow-x-auto border-b border-border bg-surface-sidebar px-2.5 py-3 md:w-52 md:flex-col md:border-b-0 md:border-r"
            >
              {SETTINGS_TABS.map((item) => {
                const active = item.id === tab;
                return (
                  <a
                    key={item.id}
                    href={`/settings/${item.id}`}
                    aria-current={active ? "page" : undefined}
                    onClick={(event) => {
                      // A real link (so it can be opened in a new tab), but a
                      // plain click swaps the pane in place, over the same page.
                      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0)
                        return;
                      event.preventDefault();
                      openSettings(item.id);
                    }}
                    className={cn(
                      "flex h-control-md shrink-0 items-center gap-[9px] rounded-item px-2.5 text-sm transition-colors duration-fast",
                      active
                        ? "bg-surface-selected font-label text-text"
                        : "text-text-muted hover:bg-surface-hover hover:text-text",
                    )}
                  >
                    <item.icon
                      className={cn(
                        "size-[15px] shrink-0",
                        active ? "text-accent" : "text-text-subtle",
                      )}
                      strokeWidth={1.75}
                      aria-hidden
                    />
                    <span>{t(item.labelKey)}</span>
                  </a>
                );
              })}
            </nav>
            <div
              className="min-w-0 flex-1 overflow-y-auto px-7 py-5"
              data-testid={`settings-pane-${tab}`}
            >
              <Pane />
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
