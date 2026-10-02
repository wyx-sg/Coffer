// src/components/shell/SidebarToggle.tsx — the button that collapses and expands the primary sidebar.
//
// Two placements share it: in the logo row (browser, and the rail's expand
// control under the mark) and, in the desktop shell, as the one fixed control
// in the title strip beside the traffic lights, where it never moves when the
// sidebar changes width.
import { useTranslation } from "react-i18next";
import { PanelLeft, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { shortcutLabel } from "@/lib/shortcuts";
import { cn } from "@/lib/utils";

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  /** `titlebar`: one icon in both states, with the shortcut in the tooltip. */
  placement: "row" | "titlebar";
  controls?: string;
  className?: string;
}

export function SidebarToggle({ collapsed, onToggle, placement, controls, className }: Props) {
  const { t } = useTranslation();
  const label = t(collapsed ? "nav.expand" : "nav.collapse");
  const Icon = placement === "titlebar" ? PanelLeft : collapsed ? PanelLeftOpen : PanelLeftClose;
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
          <Icon className="size-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side={placement === "titlebar" ? "bottom" : "right"}>
        {placement === "titlebar" ? `${label} (${shortcutLabel("B")})` : label}
      </TooltipContent>
    </Tooltip>
  );
}
