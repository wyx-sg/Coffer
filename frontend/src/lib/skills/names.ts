// frontend/src/lib/skills/names.ts
// A list of names as a sentence reads it: "pdf", "pdf and release-notes",
// "frontend-design, pdf and release-notes" — in the reader's language.

export function joinNames(names: readonly string[], locale: string): string {
  if (names.length === 0) return "";
  try {
    return new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(names);
  } catch {
    return names.join(", ");
  }
}
