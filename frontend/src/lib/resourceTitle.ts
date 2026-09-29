// src/lib/resourceTitle.ts
// The one rule for what a resource is called on screen (spec resource-framework
// "Carry an optional editable title on the kinds that have one"): its title when one is
// set, its name otherwise. Every list row, detail header and confirmation goes
// through `displayName` so no surface re-derives it.

/** The longest title the daemon accepts (`resources.title`). */
export const TITLE_MAX_LENGTH = 80;

/** Anything a surface names: every kind's wire row carries both fields. */
export interface Titled {
  name: string;
  title?: string | null;
}

/** The title a person chose, or `null` when none is set. */
export function titleOf(r: Titled): string | null {
  const title = r.title?.trim();
  return title ? title : null;
}

/** What a surface shows where it names the resource. */
export function displayName(r: Titled): string {
  return titleOf(r) ?? r.name;
}

/** The text a list's search box matches: the title AND the name, so a row is
 *  found by what the page shows and by what an agent sees. */
export function searchableName(r: Titled): string {
  const title = titleOf(r);
  return title ? `${title} ${r.name}` : r.name;
}

/** The PATCH value for a title field's text: blank clears it. */
export function titlePatchValue(text: string): string | null {
  const trimmed = text.trim();
  return trimmed ? trimmed : null;
}
