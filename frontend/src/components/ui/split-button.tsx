// src/components/ui/split-button.tsx
// A split button (Foundations 0.7.04): the main part runs the default action, the
// ▾ part opens a menu of the others. Both parts share one outline and one height.
// A tooltip may name what the main part does; when the button is disabled the
// tooltip says why (a disabled button gets no pointer events, so the wrapper
// carries it). Used by the hand-off and by the rows of the session lists.
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface Props {
  /** The main part's text. */
  label: ReactNode;
  icon?: ReactNode;
  onClick: () => void;
  /** The ▾ trigger's accessible name and the menu's, e.g. "More options". */
  menuLabel: string;
  /** The menu's items; with none the ▾ part is left out. */
  actions: readonly MenuAction[];
  size?: "sm" | "default" | "lg";
  /** Disables both parts. */
  disabled?: boolean;
  /** Shown on hover/focus of the main part; with `disabled`, it is the reason. */
  tooltip?: string;
  /** The main part's accessible name when its text is shorter than the action. */
  ariaLabel?: string;
  className?: string;
}

export function SplitButton({
  label,
  icon,
  onClick,
  menuLabel,
  actions,
  size = "default",
  disabled = false,
  tooltip,
  ariaLabel,
  className,
}: Props) {
  const small = size === "sm";
  const hasMenu = actions.length > 0 || disabled;
  const main = (
    <Button
      type="button"
      variant="outline"
      size={size}
      disabled={disabled}
      aria-label={ariaLabel}
      className={cn(hasMenu && "rounded-r-none border-r-0")}
      onClick={onClick}
    >
      {icon}
      {label}
    </Button>
  );
  return (
    <div className={cn("inline-flex", className)}>
      {tooltip ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              {disabled ? (
                <span className="inline-flex" tabIndex={0}>
                  {main}
                </span>
              ) : (
                main
              )}
            </TooltipTrigger>
            <TooltipContent>{tooltip}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        main
      )}
      {hasMenu ? (
        <ActionMenu
          label={menuLabel}
          actions={actions}
          trigger={
            <Button
              type="button"
              variant="outline"
              size={size}
              disabled={disabled}
              aria-label={menuLabel}
              aria-haspopup="menu"
              className={cn("rounded-l-none px-0", small ? "w-6" : size === "lg" ? "w-8" : "w-7")}
            >
              <ChevronDown aria-hidden className="!size-3" />
            </Button>
          }
        />
      ) : null}
    </div>
  );
}
