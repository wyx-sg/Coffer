// src/components/palette/usePaletteModel.ts — what the open palette shows for a query: its groups, in order, and the state lines under them.
//
// An empty query shows Recent (the last few choices) and every page; a query
// shows the single best hit as "Best match", then Pages, then one group per
// object kind. Objects are listed once the daemon has answered: while it cannot
// be reached the palette lists pages only.
import { useCallback, useMemo, useState } from "react";

import { useDaemonStatus } from "@/lib/hooks/useDaemon";
import { isFeatureOn, useFeatureMap } from "@/lib/hooks/useFeatures";
import { NAV_ENTRIES } from "@/lib/navigation";
import {
  KIND_PAGE,
  OBJECT_KINDS,
  objectItem,
  searchGroups,
  type ObjectKind,
  type PaletteItem,
} from "./paletteItems";
import { readRecent, resolveRecent, type RecentItem } from "./paletteRecent";
import { usePageItems, type KindState } from "./paletteSources";

/** One group as the list renders it. `recent` groups carry when each was chosen. */
type ModelGroup =
  | { key: "recent"; items: PaletteItem[]; recent: RecentItem[] }
  | { key: "best" | "pages" | ObjectKind; items: PaletteItem[] };

export interface PaletteModel {
  /** The kinds whose list hooks run now. */
  liveKinds: readonly ObjectKind[];
  onKindState: (kind: ObjectKind, state: KindState) => void;
  groups: ModelGroup[];
  /** Every row, in the order the arrow keys walk them; `key` is unique even
   *  when one entry is under Recent and Pages both. */
  visible: { key: string; item: PaletteItem }[];
  loading: boolean;
  /** Kinds whose list failed, shown only under a query. */
  failed: ObjectKind[];
  offline: boolean;
}

const NO_KINDS: readonly ObjectKind[] = [];

export function usePaletteModel(query: string): PaletteModel {
  const features = useFeatureMap();
  const daemon = useDaemonStatus();
  const offline = daemon.isError;
  const reachable = !offline && daemon.data !== undefined;
  const [kinds, setKinds] = useState<Partial<Record<ObjectKind, KindState>>>({});
  // Read once per opening: the palette body mounts only while it is open.
  const [stored] = useState(readRecent);

  const onKindState = useCallback((kind: ObjectKind, state: KindState) => {
    setKinds((prev) => ({ ...prev, [kind]: state }));
  }, []);

  // A kind that lives on a switched-off feature's page is not listed, and its
  // list is not asked for (spec experimental-features "Close every surface of
  // a switched-off feature").
  const liveKinds = useMemo<readonly ObjectKind[]>(
    () =>
      reachable
        ? OBJECT_KINDS.filter((kind) =>
            isFeatureOn(features, NAV_ENTRIES.find((e) => e.to === KIND_PAGE[kind])?.feature),
          )
        : NO_KINDS,
    [reachable, features],
  );

  const pages = usePageItems(features);

  const objects = useMemo<PaletteItem[]>(
    () =>
      liveKinds.flatMap((kind) => {
        const state = kinds[kind];
        if (!state || state.status !== "success") return [];
        return state.items.map((obj) => objectItem(kind, obj));
      }),
    [liveKinds, kinds],
  );

  const searching = query.trim() !== "";
  const groups = useMemo<ModelGroup[]>(() => {
    if (searching) return searchGroups(pages, objects, query);
    const recent = resolveRecent(stored, { pages, liveKinds, kinds, objects });
    const out: ModelGroup[] = [];
    if (recent.length > 0) out.push({ key: "recent", items: recent.map((r) => r.item), recent });
    // Pages stays whole — a page under Recent keeps its place in it too.
    out.push({ key: "pages", items: pages });
    return out;
  }, [searching, pages, objects, query, stored, liveKinds, kinds]);

  const visible = useMemo(
    () => groups.flatMap((g) => g.items.map((item) => ({ key: `${g.key}-${item.id}`, item }))),
    [groups],
  );

  const loading =
    searching &&
    ((!offline && !reachable) ||
      liveKinds.some((kind) => (kinds[kind]?.status ?? "pending") === "pending"));
  const failed = searching ? liveKinds.filter((kind) => kinds[kind]?.status === "error") : [];

  return { liveKinds, onKindState, groups, visible, loading, failed, offline };
}
