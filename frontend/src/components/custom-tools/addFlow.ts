// src/components/custom-tools/addFlow.ts — the state the Add custom tool flow carries from step to step.
import type { KeyValueSecretRow } from "@/components/secret/secretValue";
import type { Scope } from "@/lib/api/scope";
import type { ReachMode } from "@/lib/reach/reachState";

export type AddStep = "choose" | "newGroup" | "request";

/** The group select's "make a new one" entry. */
export const NEW_GROUP = "__new__";

/** Where the flow opens: the first-run card opens a new group; a group's Add
 *  request opens the request form on that group. */
export interface AddStart {
  target?: string;
  step?: "choose" | "newGroup" | "request";
}

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

export function newGroupDraft(name = ""): GroupDraft {
  return { name, description: "", baseUrl: "", headers: [], reach: EVERY_AGENT };
}
