// src/components/palette/CommandPalette.tsx — the ⌘K palette: jump to any page, Settings tab or object.
//
// Spec web-ui "Jump to any page or object from a command palette" (change
// revise-web-ui-ia, design decision 6). The palette only navigates: every entry
// is a page, a Settings tab or an object's detail page, and choosing one sends
// no request that changes state. It reads the list routes the pages already
// read, through the same hooks and so the same query keys, and adds none.
//
// Pages are static data (`lib/navigation`), so they are usable at once whatever
// the daemon's state. Objects are fetched only while the palette is open — the
// panel's content, and with it every list hook, mounts only then — and each
// kind reports on its own, so one failing list leaves the others working.
// An empty query shows the last few choices (Recent) and every page; a query
// shows its best hit, then the rest grouped by kind (`usePaletteModel`).
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { DialogOverlay } from "@/components/ui/dialog";
import { useHereOriginState } from "@/lib/origin";
import { useOpenSettings } from "@/lib/settingsModal";
import { cn } from "@/lib/utils";
import { Kbd } from "@/components/ui/kbd";
import { Hint } from "./PaletteParts";
import { PaletteList } from "./PaletteList";
import type { PaletteItem } from "./paletteItems";
import { rememberChoice } from "./paletteRecent";
import { KindSource } from "./KindSource";
import { usePaletteModel } from "./usePaletteModel";

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const { t } = useTranslation();
  // The palette has no Radix Trigger (⌘K and the sidebar control open it), and
  // a modal Radix dialog returns focus only to its Trigger. So remember what
  // held focus as it opens — a layout effect runs before the dialog moves
  // focus into its field — and hand focus back there on close.
  const returnFocus = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (open) {
      const active = document.activeElement;
      returnFocus.current = active instanceof HTMLElement ? active : null;
    }
  }, [open]);
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogOverlay />
        <DialogPrimitive.Content
          aria-label={t("palette.label")}
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            returnFocus.current?.focus();
          }}
          className={cn(
            "fixed left-[50%] top-[120px] z-dialog flex max-h-[calc(100vh-160px)] w-[600px] max-w-[calc(100%-2rem)] translate-x-[-50%] flex-col overflow-hidden rounded-2xl bg-surface-raised text-sm text-text shadow-overlay outline-none",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[.98] data-[state=open]:duration-slow data-[state=open]:ease-out",
            "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-fast data-[state=closed]:ease-in",
          )}
        >
          <DialogPrimitive.Title className="sr-only">{t("palette.label")}</DialogPrimitive.Title>
          <PaletteBody close={() => onOpenChange(false)} />
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function PaletteBody({ close }: { close: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const origin = useHereOriginState();
  const openSettings = useOpenSettings();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const model = usePaletteModel(query);
  const { visible } = model;
  const listRef = useRef<HTMLDivElement>(null);
  const baseId = useId();
  const selected = visible.length === 0 ? -1 : Math.min(active, visible.length - 1);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (selected < 0) return;
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${selected}"]`);
    node?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  const choose = (item: PaletteItem) => {
    rememberChoice(item);
    close();
    if (item.target.type === "settings") openSettings(item.target.tab);
    else navigate(item.target.to, { state: origin });
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (visible.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((selected + step + visible.length) % visible.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const row = visible[selected];
      if (row) choose(row.item);
    }
  };

  const listboxId = `${baseId}-listbox`;

  return (
    <>
      {model.liveKinds.map((kind) => (
        <KindSource key={kind} kind={kind} query={query} onState={model.onKindState} />
      ))}
      <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border-subtle px-4">
        <Search className="size-4 shrink-0 text-text-muted" aria-hidden />
        {/* No autoFocus: the dialog focuses its first field on open, and an
            autoFocus would run first and hide from Radix the element focus
            must return to on close. */}
        <input
          role="combobox"
          aria-expanded
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-activedescendant={selected >= 0 ? `${baseId}-${visible[selected].key}` : undefined}
          aria-label={t("palette.placeholder")}
          placeholder={t("palette.placeholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          className="h-full min-w-0 flex-1 bg-transparent text-md text-text outline-none placeholder:text-text-muted"
        />
        <button
          type="button"
          tabIndex={-1}
          aria-label={t("palette.close")}
          onClick={close}
          className="shrink-0 cursor-pointer"
        >
          <Kbd>esc</Kbd>
        </button>
      </div>
      <div ref={listRef} className="flex min-h-0 flex-1 flex-col">
        <PaletteList
          model={model}
          query={query}
          listboxId={listboxId}
          baseId={baseId}
          selected={selected}
          onHover={setActive}
          onChoose={choose}
        />
      </div>
      <div className="flex shrink-0 items-center gap-3.5 border-t border-border-subtle px-4 py-2 text-xs text-text-muted">
        <Hint keys="↑↓" label={t("palette.navigate")} />
        <Hint keys="↵" label={t("palette.open")} />
        <Hint keys="esc" label={t("palette.close")} />
        <span className="ml-auto truncate">{t("palette.footerNote")}</span>
      </div>
    </>
  );
}
