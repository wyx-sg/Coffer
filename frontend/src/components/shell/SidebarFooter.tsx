// src/components/shell/SidebarFooter.tsx — the foot of the sidebar: the labelled Settings row above the daemon's state.
//
// Settings is not a navigation entry: this row (gear + the word, the gear alone
// with a tooltip on the collapsed rail) opens it as a modal over the page, and
// shows active only while the modal is open (spec web-ui "Open Settings as a
// modal from the sidebar footer"). Below it, the daemon's state in plain words;
// clicking it opens Settings on Daemon (spec web-ui "Show the daemon's state in
// the shell footer").
import { useTranslation } from "react-i18next";
import { Settings as SettingsIcon } from "lucide-react";

import { StatusDot } from "@/components/status/StatusDot";
import type { StatusTone } from "@/components/status/statusTone";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useOpenSettings, useSettingsOpen } from "@/lib/settingsModal";
import { formatVersion } from "@/lib/version";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import { useDaemonFooterState, type DaemonFooterState } from "./useDaemonFooterState";

const TONE: Record<DaemonFooterState["kind"], StatusTone> = {
  connecting: "off",
  running: "ok",
  stopping: "warn",
  offline: "err",
};

function useDaemonLabel(state: DaemonFooterState): string {
  const { t } = useTranslation();
  switch (state.kind) {
    case "connecting":
      return t("nav.daemon.connecting");
    case "running":
      return state.outOfDate
        ? t("nav.daemon.outOfDate", { port: state.port })
        : t("nav.daemon.running", { port: state.port });
    case "stopping":
      return t("nav.daemon.stopping");
    case "offline":
      return t("nav.daemon.offline");
  }
}

/** A row that carries a tooltip only on the collapsed rail, where its words are gone. */
function RailTooltip({
  collapsed,
  label,
  children,
}: {
  collapsed: boolean;
  label: string;
  children: JSX.Element;
}) {
  if (!collapsed) return children;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

export function SidebarFooter({ collapsed }: { collapsed: boolean }) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  const settingsOpen = useSettingsOpen();
  const state = useDaemonFooterState();
  const daemonLabel = useDaemonLabel(state);
  const tone: StatusTone = state.kind === "running" && state.outOfDate ? "warn" : TONE[state.kind];
  const settingsLabel = t("nav.settings");
  // The visible words fit the sidebar's width; the accessible name and the
  // rail's tooltip carry the whole sentence.
  const shortLabel =
    state.kind === "running" && !state.outOfDate
      ? t("nav.daemon.runningShort", { port: state.port })
      : daemonLabel;

  return (
    <div className={cn("flex flex-col gap-0.5 px-2.5 pb-2", collapsed && "items-center")}>
      <RailTooltip collapsed={collapsed} label={`${settingsLabel}  ${shortcutLabel(",")}`}>
        <button
          type="button"
          onClick={() => openSettings("general")}
          aria-label={collapsed ? settingsLabel : undefined}
          aria-pressed={settingsOpen}
          data-testid="sidebar-settings"
          className={cn(
            "flex h-7 w-full items-center rounded-item text-sm transition-colors duration-fast",
            collapsed ? "justify-center px-2" : "gap-[9px] px-2.5 text-left",
            settingsOpen
              ? "bg-surface-selected font-label text-text"
              : "font-book text-text-muted hover:bg-surface-hover hover:text-text",
          )}
        >
          <SettingsIcon
            className={cn(
              "size-[15px] shrink-0",
              settingsOpen ? "text-accent" : "text-text-subtle",
            )}
            strokeWidth={1.75}
            aria-hidden
          />
          {!collapsed ? <span className="flex-1 truncate">{settingsLabel}</span> : null}
        </button>
      </RailTooltip>
      <RailTooltip collapsed={collapsed} label={daemonLabel}>
        <button
          type="button"
          onClick={() => openSettings("daemon")}
          aria-label={daemonLabel}
          data-testid="sidebar-daemon"
          data-state={state.kind}
          className={cn(
            "flex w-full items-center rounded-item text-xs text-text-muted transition-colors duration-fast hover:bg-surface-hover hover:text-text",
            collapsed ? "h-7 justify-center px-2" : "min-h-7 gap-2 px-2.5 py-1.5 text-left",
          )}
        >
          <StatusDot tone={tone} />
          {!collapsed ? <span className="min-w-0 flex-1 truncate">{shortLabel}</span> : null}
          {!collapsed && state.kind === "running" ? (
            <span className="shrink-0 text-text-subtle" data-testid="sidebar-version">
              {formatVersion(state.version)}
            </span>
          ) : null}
        </button>
      </RailTooltip>
    </div>
  );
}
