// src/components/shell/SidebarToggle.tsx — the button that collapses and expands the primary sidebar.
//
// Two placements share it: in the logo row (browser, and the rail's expand
// control under the mark) and, in the desktop shell, in the title strip beside
// the traffic lights, where it never moves when the sidebar changes width.
// Both draw the one PanelLeft icon in both states and show the ⌘\ shortcut in
// the tooltip.
import { useTranslation } from "react-i18next";
import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  /** Where it sits: the tooltip opens beside a row, below the title strip. */
  placement: "row" | "titlebar";
  controls?: string;
  className?: string;
}

export function SidebarToggle({ collapsed, onToggle, placement, controls, className }: Props) {
  const { t } = useTranslation();
  const label = t(collapsed ? "nav.expand" : "nav.collapse");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onToggle}
          aria-label={label}
          aria-expanded={!collapsed}
          aria-controls={controls}
          className={cn("shrink-0 text-text-subtle", className)}
        >
          <PanelLeft className="size-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side={placement === "titlebar" ? "bottom" : "right"}>
        {`${label} ${shortcutLabel("\\")}`}
      </TooltipContent>
    </Tooltip>
  );
}
