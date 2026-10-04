// src/components/shell/WindowTitleStrip.tsx — the app's own title bar, standing in for the native one.
//
// Where the native title bar is gone (macOS shell), a 38px bar along the top
// edge (the sidebar's colour, no rule under it) takes its place: dragging it
// moves the window and a double-click zooms it. It holds only window-level
// controls (board 1.1.02): the traffic lights the system draws, just right of
// them the sidebar toggle, then ← and → through the app's history. The
// controls sit on the strip's centre line (y 19, where
// `trafficLightPosition` y 17 centres the lights too), fixed, so they stay put as the
// sidebar changes width; they have their own pointer events instead of being
// drag handles. In full screen the lights are hidden and the controls start at
// x 14. With the sidebar expanded, its right edge runs up through the strip as
// a 1px line; collapsed, the strip runs across and the rail sits under it. To the
// right of the sidebar a page may register one title row (titleBarSlot.tsx).
import { useTranslation } from "react-i18next";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHistoryNav } from "@/lib/hooks/useHistoryNav";
import { useWindowFullscreen } from "@/lib/hooks/useWindowFullscreen";
import { shortcutLabel } from "@/lib/shortcuts";
import { SidebarToggle } from "./SidebarToggle";

// The three lights (14px frames, 20px apart from x 20) end at x 74; the toggle's
// 28px button starts 8px later, so its icon sits 14px after the last light.
const CONTROLS_LEFT = 82;
const CONTROLS_LEFT_FULLSCREEN = 14;
const RAIL_WIDTH = 56;
// Where the toggle and the two arrows end (82 + 3 × 28), plus a gap.
const SLOT_AFTER_CONTROLS = 186;

interface Props {
  /** Below md the sidebar is always the rail, so there is nothing to toggle. */
  showToggle: boolean;
  collapsed: boolean;
  onToggle: () => void;
  /** The expanded sidebar's width in px; its right edge continues up through the strip. */
  sidebarWidth: number;
  onBack: () => void;
  onForward: () => void;
  /** Receives the element to the right of the sidebar that a page may put its title row in. */
  onSlot?: (el: HTMLElement | null) => void;
}

function HistoryButton({
  label,
  keyLabel,
  disabled,
  onClick,
  children,
}: {
  label: string;
  keyLabel: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
          className="shrink-0 text-text-subtle disabled:opacity-[.45]"
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{`${label} ${shortcutLabel(keyLabel)}`}</TooltipContent>
    </Tooltip>
  );
}

export function WindowTitleStrip({
  showToggle,
  collapsed,
  onToggle,
  sidebarWidth,
  onBack,
  onForward,
  onSlot,
}: Props) {
  const { t } = useTranslation();
  const fullscreen = useWindowFullscreen();
  const history = useHistoryNav();
  // 32px in from the sidebar's edge; with the rail collapsed the strip's own
  // controls run on past it, so the title starts after them.
  const slotLeft = collapsed ? Math.max(RAIL_WIDTH + 32, SLOT_AFTER_CONTROLS) : sidebarWidth + 32;
  return (
    <div
      data-tauri-drag-region
      data-testid="window-drag-region"
      className="fixed inset-x-0 top-0 z-sticky h-[var(--titlebar-inset)] bg-surface-sidebar"
    >
      <div
        data-tauri-drag-region="false"
        data-testid="title-controls"
        className="absolute inset-y-0 flex items-center gap-0.5"
        style={{ left: fullscreen ? CONTROLS_LEFT_FULLSCREEN : CONTROLS_LEFT }}
      >
        {showToggle ? (
          <SidebarToggle
            placement="titlebar"
            collapsed={collapsed}
            onToggle={onToggle}
            controls="sidebar"
            className="mr-0.5"
          />
        ) : null}
        <HistoryButton
          label={t("nav.back")}
          keyLabel="["
          disabled={!history.canGoBack}
          onClick={onBack}
        >
          <ArrowLeft className="size-[15px]" />
        </HistoryButton>
        <HistoryButton
          label={t("nav.forward")}
          keyLabel="]"
          disabled={!history.canGoForward}
          onClick={onForward}
        >
          <ArrowRight className="size-[15px]" />
        </HistoryButton>
      </div>
      {/* The one page-level exception: an open conversation's title row. The
          container passes pointer events through (so empty space still drags the
          window); its own children take them. */}
      <div
        ref={onSlot}
        data-testid="title-slot"
        className="pointer-events-none absolute inset-y-0 right-0 flex min-w-0 items-center gap-2.5 pr-4 [&>*]:pointer-events-auto"
        style={{ left: slotLeft }}
      />
      {collapsed ? null : (
        <span
          aria-hidden
          data-testid="title-sidebar-edge"
          className="absolute inset-y-0 w-px bg-border"
          style={{ left: sidebarWidth }}
        />
      )}
    </div>
  );
}
