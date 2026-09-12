// frontend/src/kinds/channel/modelCuration.ts
//
// The channel's own model curation (spec channels FR-071) as pure rules, kept
// apart from the form schema so the dialogs, the fields component and the
// planning step all read one definition of what these two values mean:
//
// * `default_model` — what a NEW conversation on this channel opens on. Blank
//   pins nothing and the agent's CLI default applies.
// * `models` — the allowed range. EMPTY means NOT CURATED (every model the
//   bound agent offers), never "no models".
import { z } from "zod";

/** The two curation fields, shared by every channel type's form schema. */
export const modelCurationFields = {
  default_model: z.string().optional(),
  models: z.array(z.string()).optional(),
};

/**
 * The backend's rule, mirrored in the form: a channel must not start
 * conversations on a model it then refuses. Only bites when the range is
 * curated — with `models` empty there is nothing to be outside of, and the
 * pinned id is free text handed to the CLI verbatim.
 */
export function defaultModelOutOfRange(
  defaultModel: string | undefined,
  models: string[] | undefined,
): boolean {
  const pinned = defaultModel?.trim();
  const range = models ?? [];
  return Boolean(pinned) && range.length > 0 && !range.includes(pinned as string);
}

/**
 * The curation keys a config carries, omitted when they say nothing: an absent
 * `default_model` is "not pinned" and an absent `models` is "not curated",
 * which are exactly the backend's defaults. Writing `null` / `[]` explicitly
 * would only add noise to the stored config.
 */
export function modelCurationConfig(
  defaultModel: string | undefined,
  models: string[] | undefined,
): Record<string, unknown> {
  const pinned = defaultModel?.trim();
  const range = models ?? [];
  return {
    ...(pinned ? { default_model: pinned } : {}),
    ...(range.length > 0 ? { models: range } : {}),
  };
}
