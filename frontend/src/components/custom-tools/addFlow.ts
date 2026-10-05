// src/components/custom-tools/addFlow.ts — the state the Add custom tool flow carries from step to step.
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import type { OpenApiReading } from "@/lib/api/customTools";
import type { Scope } from "@/lib/api/scope";
import type { ReachMode } from "@/lib/reach/reachState";

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

/** The reach a new group starts with: the standard control's mode, and the agents ticked. */
export interface ReachDraft {
  mode: ReachMode;
  scope: Scope | null;
}

export const EVERY_AGENT: ReachDraft = { mode: "everywhere", scope: null };

/** The group being made, as the steps fill it in. Nothing of it is saved
 *  until the flow's last button. */
export interface GroupDraft {
  name: string;
  /** What the API is for; agents read it when they search for a tool. */
  description: string;
  baseUrl: string;
  /** Headers every call sends, a secret only from Coffer. */
  headers: KeyValueSecretRow[];
  reach: ReachDraft;
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
  return { name, description: "", baseUrl: "", headers: [], reach: EVERY_AGENT };
}

export function newImportDraft(): ImportDraft {
  return { mode: "url", url: "", fileName: "", document: "", reading: null, picked: [] };
}

/** The operations picked by default: the ones that do not change data. */
export function defaultPicks(reading: OpenApiReading): string[] {
  return reading.operations.filter((op) => (op.tool.method ?? "GET") === "GET").map((op) => op.key);
}

/** The rows a spec's security scheme pre-fills: one row named for its header, no value yet. */
export function headerRowsFromSpec(authHeader: string | null): KeyValueSecretRow[] {
  return authHeader ? [{ key: authHeader, value: { kind: "plain", value: "" } }] : [];
}
