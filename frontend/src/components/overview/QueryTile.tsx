// src/components/overview/QueryTile.tsx — one Health tile over one list query: loading, failed with Retry, or its content.
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { NAV_ENTRIES } from "@/lib/navigation";
import type { Area } from "@/lib/overview/health";
import { HealthTile, type TileContent } from "./HealthTile";

/** Render one tile over one list query: loading, failed, or its content. */
export function QueryTile<T>({
  area,
  query,
  content,
}: {
  area: Area;
  query: UseQueryResult<T>;
  content: (data: T) => TileContent;
}) {
  const { t } = useTranslation();
  const entry = NAV_ENTRIES.find((e) => e.to === area.to);
  if (!entry) return null;
  const label = t(entry.labelKey);
  const state = query.isPending
    ? ({ kind: "loading" } as const)
    : query.isError
      ? ({ kind: "error", error: query.error, retry: () => void query.refetch() } as const)
      : ({ kind: "ready", content: content(query.data as T) } as const);
  return <HealthTile to={area.to} label={label} icon={entry.icon} state={state} />;
}
