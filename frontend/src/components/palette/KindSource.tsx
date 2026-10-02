// src/components/palette/KindSource.tsx — runs one kind's list hook while the palette is open and reports its state.
import { useEffect } from "react";

import type { ObjectKind } from "./paletteItems";
import { KIND_LIST_HOOKS, type KindState } from "./paletteSources";

/** Runs one kind's list hook and reports what it says. Mounted per kind, and
 *  only while the palette is open and the daemon has answered. */
export function KindSource({
  kind,
  query,
  onState,
}: {
  kind: ObjectKind;
  /** What the palette's box holds. */
  query: string;
  onState: (kind: ObjectKind, state: KindState) => void;
}) {
  const useList = KIND_LIST_HOOKS[kind];
  const { status, items } = useList(query);
  useEffect(() => {
    onState(kind, { status, items });
  }, [kind, status, items, onState]);
  return null;
}
