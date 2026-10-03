// src/components/shell/SidebarSearch.tsx — the sidebar's search control: opens the command palette (⌘K).
//
// Expanded it is a bordered field with the shortcut; on the rail a borderless
// 32 × 28 icon button in the subtle ink (the sidebar component board).
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

interface Props {
  collapsed: boolean;
  onOpen: () => void;
}

export function SidebarSearch({ collapsed, onOpen }: Props) {
  const { t } = useTranslation();
  const label = t("nav.search");
  const button = (
    <button
      type="button"
      onClick={onOpen}
      aria-label={collapsed ? label : undefined}
      data-testid="sidebar-search"
      className={cn(
        "flex items-center text-sm text-text-subtle transition-colors duration-fast hover:bg-surface-hover hover:text-text",
        collapsed
          ? "h-7 w-8 justify-center rounded-item"
          : "mx-0.5 h-control-md w-[calc(100%-4px)] gap-2 rounded-md border border-border bg-surface-raised pl-2.5 pr-2",
      )}
    >
      <Search className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
      {!collapsed ? (
        <>
          <span className="flex-1 truncate text-left">{label}</span>
          <Kbd aria-hidden>{shortcutLabel("k")}</Kbd>
        </>
      ) : null}
    </button>
  );
  return (
    <div className={cn("px-2.5", collapsed && "flex justify-center")}>
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent side="right">{`${label}  ${shortcutLabel("k")}`}</TooltipContent>
        </Tooltip>
      ) : (
        button
      )}
    </div>
  );
}
