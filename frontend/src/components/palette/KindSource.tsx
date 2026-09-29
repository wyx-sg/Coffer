// src/components/palette/KindSource.tsx — runs one kind's list hook while the palette is open and reports its state.
import { useEffect } from "react";

import type { ObjectKind } from "./paletteItems";
import { KIND_LIST_HOOKS, type KindState } from "./paletteSources";

/** Runs one kind's list hook and reports what it says. Mounted per kind, and
 *  only for kinds the palette may list, so a switched-off feature is never
 *  asked for. */
export function KindSource({
  kind,
  onState,
}: {
  kind: ObjectKind;
  onState: (kind: ObjectKind, state: KindState) => void;
}) {
  const useList = KIND_LIST_HOOKS[kind];
  const { status, items } = useList();
  useEffect(() => {
    onState(kind, { status, items });
  }, [kind, status, items, onState]);
  return null;
}
