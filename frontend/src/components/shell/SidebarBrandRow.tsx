// src/components/shell/SidebarBrandRow.tsx — the sidebar's top row in the browser build.
//
// The brand mark linking home and, at md and wider, the collapse toggle. The
// desktop shell has neither: its title strip holds the traffic lights, the
// toggle and the history arrows, and the sidebar starts at the search box.
// Expanded the row is 44px high, its mark 20px with the 14px
// wordmark; on the rail the mark sits 10px from the top with the toggle under it.
import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";
import { CofferLogo } from "../brand/CofferLogo";
import { SidebarToggle } from "./SidebarToggle";

interface Props {
  collapsed: boolean;
  /** Collapsing is only possible at md+ (narrower viewports are always the icon rail). */
  showToggle: boolean;
  onToggle: () => void;
}

export function SidebarBrandRow({ collapsed, showToggle, onToggle }: Props) {
  return (
    <div
      className={cn(
        "flex",
        collapsed
          ? "flex-col items-center gap-1.5 px-2 pt-2.5"
          : "h-11 shrink-0 items-center justify-between pl-5 pr-3",
      )}
    >
      <Link
        to="/"
        className="flex items-center rounded-item text-text"
        aria-label={collapsed ? "Coffer" : undefined}
      >
        <CofferLogo size={20} markOnly={collapsed} />
      </Link>
      {/* The same spot, under the mark on the rail, expands it again. */}
      {showToggle ? (
        <SidebarToggle
          placement="row"
          collapsed={collapsed}
          onToggle={onToggle}
          controls="sidebar"
        />
      ) : null}
    </div>
  );
}
