// src/components/shell/SidebarFooter.tsx — the foot of the sidebar: the update card, the Settings row and the daemon/version row.
//
// Settings is not a navigation entry: this row (gear + the word, the gear alone
// with a tooltip on the collapsed rail) opens it as a modal over the page, and
// shows active only while the modal is open (spec web-ui "Open Settings as a
// modal from the sidebar footer"). Below it, the daemon's state in plain words
// with the app version on the right; clicking it opens the version menu —
// version, daemon, theme, language, documentation, updates (spec web-ui "Show
// the daemon's state in the shell footer"). On the rail the row is the state's
// dot, and the rail's expand button sits between the gear and the dot
// (board 1.2.02).
import { useTranslation } from "react-i18next";
import { PanelLeftOpen, Settings as SettingsIcon } from "lucide-react";

import { StatusDot } from "@/components/status/StatusDot";
import type { StatusTone } from "@/lib/statusTone";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useOpenSettings, useSettingsOpen } from "@/lib/settingsModal";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import { UpdateCard } from "./UpdateCard";
import { VersionMenu } from "./VersionMenu";
import { useDaemonFooterState, type DaemonFooterState } from "./useDaemonFooterState";

const TONE: Record<DaemonFooterState["kind"], StatusTone> = {
  connecting: "off",
  running: "ok",
  stopping: "warn",
  reconnecting: "warn",
  offline: "err",
};

/** The whole sentence (accessible name, rail tooltip) and the short words the row shows. */
function useDaemonLabels(state: DaemonFooterState): { full: string; short: string } {
  const { t } = useTranslation();
  switch (state.kind) {
    case "connecting":
      return { full: t("nav.daemon.connecting"), short: t("nav.daemon.connecting") };
    case "running":
      return state.outOfDate
        ? {
            full: t("nav.daemon.outOfDate", { port: state.port }),
            short: t("nav.daemon.outOfDateShort"),
          }
        : {
            full: t("nav.daemon.running", { port: state.port }),
            short: t("nav.daemon.runningShort"),
          };
    case "stopping":
      return { full: t("nav.daemon.stopping"), short: t("nav.daemon.stopping") };
    case "reconnecting":
      return { full: t("nav.daemon.reconnecting"), short: t("nav.daemon.reconnecting") };
    case "offline":
      return { full: t("nav.daemon.offline"), short: t("nav.daemon.offline") };
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

interface Props {
  collapsed: boolean;
  /** Expands the rail; shown in the footer only while collapsed. */
  onExpand?: () => void;
}

export function SidebarFooter({ collapsed, onExpand }: Props) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  const settingsOpen = useSettingsOpen();
  const state = useDaemonFooterState();
  const labels = useDaemonLabels(state);
  const tone: StatusTone = state.kind === "running" && state.outOfDate ? "warn" : TONE[state.kind];
  const settingsLabel = t("nav.settings");
  const version = state.kind === "connecting" ? null : state.version;
  const versionText = version ? `v${version}` : null;
  // The row's accessible name carries the whole sentence and the version.
  const daemonName = versionText ? `${labels.full} · ${versionText}` : labels.full;

  const daemonRow = (
    <button
      type="button"
      aria-label={daemonName}
      data-testid="sidebar-daemon"
      // Not `data-state`: the popover trigger writes open/closed there.
      data-daemon={state.kind}
      className={cn(
        "flex items-center rounded-item text-xs text-text-muted transition-colors duration-fast hover:bg-surface-hover hover:text-text aria-expanded:bg-surface-hover",
        collapsed ? "justify-center p-1" : "w-full gap-2 px-2.5 py-2 text-left",
      )}
    >
      <StatusDot tone={tone} className={collapsed ? "size-2" : undefined} />
      {!collapsed ? (
        <>
          <span className="min-w-0 flex-1 truncate">{labels.short}</span>
          {versionText ? <span className="shrink-0 text-text-subtle">{versionText}</span> : null}
        </>
      ) : null}
    </button>
  );

  return (
    <div
      className={cn(
        "flex flex-col",
        collapsed ? "items-center gap-3.5 pb-3.5" : "gap-0.5 px-2.5 pb-2",
      )}
    >
      <UpdateCard collapsed={collapsed} />
      <RailTooltip collapsed={collapsed} label={`${settingsLabel}  ${shortcutLabel(",")}`}>
        <button
          type="button"
          onClick={() => openSettings("general")}
          aria-label={collapsed ? settingsLabel : undefined}
          aria-pressed={settingsOpen}
          data-testid="sidebar-settings"
          className={cn(
            "flex h-7 items-center rounded-item text-sm transition-colors duration-fast",
            collapsed ? "w-8 justify-center" : "w-full gap-[9px] px-2.5 text-left",
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
      {collapsed && onExpand ? (
        <RailTooltip collapsed label={t("nav.expand")}>
          <button
            type="button"
            onClick={onExpand}
            aria-label={t("nav.expand")}
            className="flex h-7 w-8 items-center justify-center rounded-item text-text-muted transition-colors duration-fast hover:bg-surface-hover hover:text-text"
          >
            <PanelLeftOpen className="size-[15px]" strokeWidth={1.75} aria-hidden />
          </button>
        </RailTooltip>
      ) : null}
      <VersionMenu
        state={state}
        tone={tone}
        stateLabel={labels.full}
        collapsed={collapsed}
        trigger={daemonRow}
        tooltip={collapsed ? daemonName : undefined}
      />
    </div>
  );
}
