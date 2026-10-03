// src/components/shell/SidebarFooter.tsx — the foot of the sidebar: the update card and the one Settings row.
//
// Settings is not a navigation entry: this single row (gear + the word, the
// gear alone with a tooltip on the collapsed rail) opens it on General as a
// modal over the page, and shows active only while the modal is open (spec
// web-ui "Open Settings as a modal from the sidebar footer"). The row carries
// no daemon state — the reconnecting bar and the offline page say that —
// and its tooltip reads "Settings ⌘,".
import { useTranslation } from "react-i18next";
import { Settings as SettingsIcon } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useOpenSettings, useSettingsOpen } from "@/lib/settingsModal";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";
import { UpdateCard } from "./UpdateCard";

interface Props {
  collapsed: boolean;
}

export function SidebarFooter({ collapsed }: Props) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  const settingsOpen = useSettingsOpen();
  const settingsLabel = t("nav.settings");

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
            onClick={() => openSettings("general")}
            aria-label={settingsLabel}
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
            {collapsed ? null : <span className="flex-1 truncate">{settingsLabel}</span>}
          </button>
        </TooltipTrigger>
        <TooltipContent side={collapsed ? "right" : "top"}>
          {`${settingsLabel}  ${shortcutLabel(",")}`}
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
