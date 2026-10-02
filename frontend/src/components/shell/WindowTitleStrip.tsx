// src/components/shell/WindowTitleStrip.tsx — the app's own title bar, standing in for the native one.
//
// Where the native title bar is gone (macOS shell), a bar along the top edge
// (the sidebar's colour, no rule under it) takes its place: dragging it moves the window and a double-click zooms it.
// The traffic lights float over it, and the sidebar toggle sits just right of
// them, on the same centre line — fixed, so it stays put as the sidebar changes width. The toggle has
// its own pointer events, so it stays clickable instead of being a drag handle.
// A detail page's "← back" link is placed to the toggle's right (titleBarSlot).
import { SidebarToggle } from "./SidebarToggle";

interface Props {
  /** Receives the element a page's "← back" link is placed in (see titleBarSlot). */
  slotRef: (el: HTMLElement | null) => void;
  /** Below md the sidebar is always the rail, so there is nothing to toggle. */
  showToggle: boolean;
  collapsed: boolean;
  onToggle: () => void;
}

export function WindowTitleStrip({ slotRef, showToggle, collapsed, onToggle }: Props) {
  return (
    <div
      data-tauri-drag-region
      data-testid="window-drag-region"
      className="fixed inset-x-0 top-0 z-sticky h-[var(--titlebar-inset)] bg-surface-sidebar"
    >
      {showToggle ? (
        <div className="absolute left-[84px] top-1/2 -translate-y-1/2" data-tauri-drag-region="false">
          <SidebarToggle
            placement="titlebar"
            collapsed={collapsed}
            onToggle={onToggle}
            controls="sidebar"
          />
        </div>
      ) : null}
      {/* The detail page's way back, right of the toggle; it takes clicks. */}
      <div
        ref={slotRef}
        data-tauri-drag-region="false"
        className="absolute inset-y-0 left-[120px] flex items-center text-sm"
      />
    </div>
  );
}
