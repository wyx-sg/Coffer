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
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { DialogOverlay } from "@/components/ui/dialog";
import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { useFeatureMap } from "@/lib/hooks/useFeatures";
import { useOpenSettings } from "@/lib/settingsModal";
import { cn } from "@/lib/utils";
import { Hint, PaletteRow, StatusLine } from "./PaletteParts";
import { filterItems, objectItem, type ObjectKind, type PaletteItem } from "./paletteItems";
import { KindSource } from "./KindSource";
import { OBJECT_KINDS, usePageItems, type KindState } from "./paletteSources";

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

const NO_KINDS: readonly ObjectKind[] = [];

function PaletteBody({ close }: { close: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const openSettings = useOpenSettings();
  const features = useFeatureMap();
  // Objects are asked for once the daemon has answered: while it cannot be
  // reached the palette lists Pages only.
  const daemon = useDaemonStatus();
  const offline = daemon.isError;
  const reachable = !offline && daemon.data !== undefined;
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [kinds, setKinds] = useState<Partial<Record<ObjectKind, KindState>>>({});
  const listRef = useRef<HTMLDivElement>(null);
  const baseId = useId();

  const onKindState = useCallback((kind: ObjectKind, state: KindState) => {
    setKinds((prev) => ({ ...prev, [kind]: state }));
  }, []);

  const liveKinds = reachable ? OBJECT_KINDS : NO_KINDS;

  const pageItems = usePageItems(features);

  const objectItems = useMemo<PaletteItem[]>(
    () =>
      liveKinds.flatMap((kind) => {
        const state = kinds[kind];
        if (!state || state.status !== "success") return [];
        const kindLabel = t(`palette.kind.${kind}`);
        return state.items.map((obj) => objectItem(kind, obj, kindLabel));
      }),
    [liveKinds, kinds, t],
  );

  const loading =
    (!offline && !reachable) ||
    liveKinds.some((kind) => (kinds[kind]?.status ?? "pending") === "pending");
  const failed = liveKinds.filter((kind) => kinds[kind]?.status === "error");

  const pages = useMemo(() => filterItems(pageItems, query), [pageItems, query]);
  const objects = useMemo(() => filterItems(objectItems, query), [objectItems, query]);
  const visible = useMemo(() => [...pages, ...objects], [pages, objects]);
  const selected = visible.length === 0 ? -1 : Math.min(active, visible.length - 1);
  const optionId = (item: PaletteItem) => `${baseId}-${item.id}`;

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (selected < 0) return;
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${selected}"]`);
    node?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  const choose = (item: PaletteItem) => {
    close();
    if (item.target.type === "settings") openSettings(item.target.tab);
    else navigate(item.target.to);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (visible.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((selected + step + visible.length) % visible.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const item = visible[selected];
      if (item) choose(item);
    }
  };

  const showObjectsGroup = !offline && (objects.length > 0 || loading || failed.length > 0);
  const noResults = query.trim() !== "" && visible.length === 0;
  const listboxId = `${baseId}-listbox`;

  const renderRow = (item: PaletteItem, index: number) => (
    <PaletteRow
      key={item.id}
      item={item}
      index={index}
      id={optionId(item)}
      selected={index === selected}
      onHover={() => index !== selected && setActive(index)}
      onChoose={() => choose(item)}
    />
  );

  return (
    <>
      {liveKinds.map((kind) => (
        <KindSource key={kind} kind={kind} onState={onKindState} />
      ))}
      <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border-subtle px-4">
        <Search className="size-4 shrink-0 text-text-subtle" aria-hidden />
        {/* No autoFocus: the dialog focuses its first field on open, and an
            autoFocus would run first and hide from Radix the element focus
            must return to on close. */}
        <input
          role="combobox"
          aria-expanded
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-activedescendant={selected >= 0 ? optionId(visible[selected]) : undefined}
          aria-label={t("palette.placeholder")}
          placeholder={t("palette.placeholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          className="h-full min-w-0 flex-1 bg-transparent text-md text-text outline-none placeholder:text-text-subtle"
        />
      </div>
      <div
        ref={listRef}
        id={listboxId}
        role="listbox"
        aria-label={t("palette.label")}
        className="min-h-0 flex-1 overflow-y-auto py-1.5"
      >
        {pages.length > 0 ? (
          <div role="group" aria-labelledby={`${baseId}-pages`}>
            <div id={`${baseId}-pages`} className="nav-group-label">
              {t("palette.pages")}
            </div>
            {pages.map((item, i) => renderRow(item, i))}
          </div>
        ) : null}
        {showObjectsGroup ? (
          <div role="group" aria-labelledby={`${baseId}-objects`}>
            <div id={`${baseId}-objects`} className="nav-group-label">
              {t("palette.objects")}
            </div>
            {objects.map((item, i) => renderRow(item, pages.length + i))}
            {loading ? <StatusLine>{t("palette.loading")}</StatusLine> : null}
            {failed.map((kind) => (
              <StatusLine key={kind} tone="danger">
                {t("palette.failed", { kind: t(`palette.kind.${kind}`) })}
              </StatusLine>
            ))}
          </div>
        ) : null}
        {noResults ? (
          <p role="status" className="px-5 py-6 text-center text-sm text-text-muted">
            {t("palette.noResults", { query: query.trim() })}
          </p>
        ) : null}
        {offline ? <StatusLine>{t("palette.offline")}</StatusLine> : null}
      </div>
      <div className="flex shrink-0 items-center gap-4 border-t border-border-subtle bg-surface-footer px-4 py-2 text-xs text-text-muted">
        <Hint keys="↑↓" label={t("palette.navigate")} />
        <Hint keys="↵" label={t("palette.open")} />
        <Hint keys="esc" label={t("palette.close")} />
      </div>
    </>
  );
}
