// frontend/src/lib/workflow/templateKeys.ts
// Deriving the identities the editor never asks for.
//
// A key is an identity the engine reads no meaning from; asking a
// developer to invent one is asking them to do the computer's filing. So a
// stage's and a task's key are slugs of their name, made unique against
// whatever is already taken.
//
// Split from `templateDraft`, which holds the EDITS. These are the one part of
// that vocabulary with no opinion about templates at all — given a name and a
// set of taken keys they answer the same way forever — and keeping them apart
// leaves each file about one thing.
import type { TemplateConfig } from "@/lib/api/workflow";

/** A lowercase slug the engine reads no meaning from — it is an identity, not
 *  a word. Empty input still has to produce something addressable. */
export function slugify(value: string, fallback: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return slug.length > 0 ? slug : fallback;
}

/** Make `candidate` unique against `taken` by suffixing, so a second "Review"
 *  is `review_2` rather than a refusal the developer has to decode. */
function unique(candidate: string, taken: Set<string>): string {
  if (!taken.has(candidate)) return candidate;
  let n = 2;
  while (taken.has(`${candidate}_${n}`)) n += 1;
  return `${candidate}_${n}`;
}

function stageKeys(config: TemplateConfig, except?: string): Set<string> {
  return new Set(config.stages.map((s) => s.key).filter((key) => key !== except));
}

/** Every node key in the template — the uniqueness scope is the WHOLE
 *  template, not the stage, because an event names a node by key alone. */
function nodeKeys(config: TemplateConfig, except?: string): Set<string> {
  return new Set(
    config.stages.flatMap((s) => s.nodes.map((n) => n.key)).filter((key) => key !== except),
  );
}

/** The key a stage with this name gets, leaving `except`'s own key free so a
 *  stage that is merely re-saved does not collide with itself. */
export function stageKeyFor(config: TemplateConfig, name: string, except?: string): string {
  return unique(slugify(name, "stage"), stageKeys(config, except));
}

export function nodeKeyFor(config: TemplateConfig, name: string, except?: string): string {
  return unique(slugify(name, "task"), nodeKeys(config, except));
}

/** An existing node, as the task dialog edits it: everything but the key.
 *
 *  Written out rather than spread-minus-key, and typed, so that a field added
 *  to `TemplateNode` is a compile error here rather than a field the dialog
 *  silently drops on save. It also settles the optional ones to the same
 *  defaults `blankNode` uses, so the dialog never holds `undefined`. */
