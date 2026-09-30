// src/components/custom-tools/addFlow.ts — the state the Add custom tool flow carries from step to step.
import type { OpenApiReading } from "@/lib/api/customTools";
import { DEFAULT_AUTH, type AuthDraft } from "@/lib/customTools/drafts";

/** The two ways into a new group. There is no script type (deferred past 1.0). */
export type AddWay = "import" | "hand";

export type AddStep = "choose" | "importSpec" | "importReview" | "newGroup" | "request";

/** The group select's "make a new one" entry. */
export const NEW_GROUP = "__new__";

/** Where the flow opens: the first-run cards pick a way into a new group; a
 *  group's Add request opens the request form on that group. */
export interface AddStart {
  target?: string;
  way?: AddWay;
  step?: "choose" | "request";
}

/** The spec an import reads: a URL, or a file's text. */
export type SpecMode = "url" | "file";

/** The group being made, as the steps fill it in. Nothing of it is saved
 *  until the flow's last button. */
export interface GroupDraft {
  name: string;
  baseUrl: string;
  auth: AuthDraft;
  /** The group's reach: agent uids, or `null` for every agent. */
  agents: string[] | null;
}

export interface ImportDraft {
  mode: SpecMode;
  url: string;
  fileName: string;
  document: string;
  reading: OpenApiReading | null;
  /** Operation keys to import. */
  picked: string[];
}

export function newGroupDraft(name = ""): GroupDraft {
  return { name, baseUrl: "", auth: { ...DEFAULT_AUTH }, agents: null };
}

export function newImportDraft(): ImportDraft {
  return { mode: "url", url: "", fileName: "", document: "", reading: null, picked: [] };
}

/** The operations picked by default: the ones that do not change data. */
export function defaultPicks(reading: OpenApiReading): string[] {
  return reading.operations.filter((op) => (op.tool.method ?? "GET") === "GET").map((op) => op.key);
}
