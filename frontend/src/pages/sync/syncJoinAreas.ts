// frontend/src/pages/sync/syncJoinAreas.ts
//
// A join preview counts files by vault area (`knowledge`, `skills`,
// `resources/mcp_server`, `state/…`, `secret`, …). The page speaks of the
// four things a person knows — Knowledge, Skills, MCP servers & tools,
// Secrets — so every `resources/*` kind folds into one, and anything else
// keeps its own name.
import type { TFunction } from "i18next";

import type { JoinPreview } from "@/lib/api/sync";

type Counts = JoinPreview["pulled"];

const ORDER = ["knowledge", "skills", "resources", "secret"];

function family(area: string): string {
  return area.split("/")[0];
}

/** "Knowledge 96 · Skills 30 · MCP servers & tools 12". */
export function areaSummary(t: TFunction, counts: Counts): string {
  const folded = new Map<string, number>();
  for (const c of counts) folded.set(family(c.area), (folded.get(family(c.area)) ?? 0) + c.files);
  const rank = (a: string) => (ORDER.includes(a) ? ORDER.indexOf(a) : ORDER.length);
  return [...folded.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([area, n]) => `${t(`sync.join.area.${area}`, { defaultValue: area })} ${n}`)
    .join(" · ");
}
