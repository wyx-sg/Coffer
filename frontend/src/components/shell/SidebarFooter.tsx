// src/components/shell/SidebarFooter.tsx — the foot of the sidebar: the update card and the one Settings row.
//
// Settings is not a navigation entry: this single row (gear + the word, the
// gear alone with a tooltip on the collapsed rail) opens it as a modal over
// the page, and shows active only while the modal is open (spec web-ui "Open
// Settings as a modal from the sidebar footer"). The daemon's state rides on
// the row: a quiet status dot at its right edge while all is well (the gear's
// corner on the rail), the state in words in its tone when it is not — and
// then the row opens Settings › Daemon. The whole sentence ("Daemon running on
// port 8000 · v1.0.0") is the row's accessible name and tooltip (spec web-ui
// "Show the daemon's state in the shell footer").
import { useTranslation } from "react-i18next";
import { Settings as SettingsIcon } from "lucide-react";

import { StatusDot } from "@/components/status/StatusDot";
import { STATUS_TONE, type StatusTone } from "@/lib/statusTone";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toneTextClass } from "@/lib/statusColors";
import { useOpenSettings, useSettingsOpen } from "@/lib/settingsModal";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import { UpdateCard } from "./UpdateCard";
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
        : { full: t("nav.daemon.running", { port: state.port }), short: "" };
    case "stopping":
      return { full: t("nav.daemon.stopping"), short: t("nav.daemon.stopping") };
    case "reconnecting":
      return { full: t("nav.daemon.reconnecting"), short: t("nav.daemon.reconnecting") };
    case "offline":
      return { full: t("nav.daemon.offline"), short: t("nav.daemon.offline") };
  }
}

interface Props {
  collapsed: boolean;
}

export function SidebarFooter({ collapsed }: Props) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  const settingsOpen = useSettingsOpen();
  const state = useDaemonFooterState();
  const labels = useDaemonLabels(state);
  const tone: StatusTone = state.kind === "running" && state.outOfDate ? "warn" : TONE[state.kind];
  const settingsLabel = t("nav.settings");
  const version = state.kind === "connecting" ? null : state.version;
  const sentence = version ? `${labels.full} · v${version}` : labels.full;
  // Healthy (or still connecting) the row stays quiet; a problem is said in words.
  const unhealthy = labels.short !== "" && state.kind !== "connecting";

  return (
    <div
      className={cn(
        "flex flex-col",
        collapsed ? "items-center gap-3.5 pb-3.5" : "gap-0.5 px-2.5 pb-2",
      )}
    >
      <UpdateCard collapsed={collapsed} />
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            // A problem lands the person on the tab that deals with it.
            onClick={() => openSettings(unhealthy ? "daemon" : "general")}
            aria-label={`${settingsLabel} · ${sentence}`}
            aria-pressed={settingsOpen}
            data-testid="sidebar-settings"
            // Not `data-state`: the tooltip trigger writes open/closed there.
            data-daemon={state.kind}
            className={cn(
              "relative flex h-7 items-center rounded-item text-sm transition-colors duration-fast",
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
            {collapsed ? (
              <StatusDot tone={tone} className="absolute bottom-1 right-1 size-1.5" />
            ) : (
              <>
                <span className="flex-1 truncate">{settingsLabel}</span>
                {unhealthy ? (
                  <span
                    className={cn(
                      "min-w-0 max-w-[60%] truncate text-xs font-label",
                      toneTextClass(STATUS_TONE[tone]),
                    )}
                  >
                    {labels.short}
                  </span>
                ) : null}
                <StatusDot tone={tone} className="shrink-0" />
              </>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side={collapsed ? "right" : "top"}>
          {`${settingsLabel}  ${shortcutLabel(",")}`}
          <br />
          {sentence}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
