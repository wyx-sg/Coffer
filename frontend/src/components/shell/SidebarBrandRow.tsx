// src/components/shell/SidebarBrandRow.tsx — the sidebar's top row in the browser build.
//
// The brand mark linking home and, at md and wider, the collapse toggle. The
// desktop shell has neither: its title strip holds the traffic lights and the
// toggle, and the sidebar starts at the search box.
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
        "flex pt-3.5",
        collapsed ? "flex-col items-center gap-2 px-2" : "items-center justify-between px-4",
      )}
    >
      <Link
        to="/"
        className="flex items-center rounded-item text-text"
        aria-label={collapsed ? "Coffer" : undefined}
      >
        <CofferLogo size={22} markOnly={collapsed} />
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
