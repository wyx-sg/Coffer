// frontend/src/components/table/TableActionButton.tsx
//
// The one look every button inside a table wears — a row's actions and a
// selection bar's actions alike: small outline button, icon + text label,
// destructive actions tinted red. Tables had drifted into four looks (ghost
// icon+text, outline text-only, solid destructive/secondary, bare ghost text),
// and the reach control that sits beside them in the same row is already an
// outline button of this size, so this is the style they converge on.
//
// A click never falls through to the row: a table action is never also "open
// this row", and a clickable row would otherwise navigate into the thing the
// action just touched.
import { forwardRef } from "react";
import type { LucideIcon } from "lucide-react";

import { Button, type ButtonProps } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The destructive tint of a table action (delete, uninstall, retire, …). */
const DESTRUCTIVE_ACTION_CLASS =
  "text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive";

interface Props extends Omit<ButtonProps, "variant" | "size" | "children"> {
  icon?: LucideIcon;
  label: string;
  destructive?: boolean;
}

export const TableActionButton = forwardRef<HTMLButtonElement, Props>(
  ({ icon: Icon, label, destructive = false, className, onClick, ...props }, ref) => (
    <Button
      ref={ref}
      type="button"
      size="sm"
      variant="outline"
      className={cn(destructive && DESTRUCTIVE_ACTION_CLASS, className)}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      {...props}
    >
      {Icon ? <Icon aria-hidden /> : null}
      {label}
    </Button>
  ),
);
TableActionButton.displayName = "TableActionButton";
