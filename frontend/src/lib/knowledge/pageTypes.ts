// frontend/src/lib/knowledge/pageTypes.ts
//
// A page's type as the Knowledge page shows it: its icon in the tree and on
// the collection's Contents, and the order Contents lists the types in (spec
// knowledge "Show a collection's contents by page type"). The five built-in
// types come first, in the order a reader starts from; a type a collection's
// README defines comes after them by name, then pages with no type. A source
// has its own icon, whatever its frontmatter says.
import {
  Box,
  Compass,
  FileQuestionMark,
  FileText,
  Lightbulb,
  Scale,
  ScrollText,
  Wrench,
  type LucideIcon,
} from "lucide-react";

/** The built-in page types, in the order Contents lists them. */
const BUILT_IN_TYPES = ["overview", "concept", "entity", "how-to", "decision"] as const;

const ICONS: Record<string, LucideIcon> = {
  overview: Compass,
  concept: Lightbulb,
  entity: Box,
  "how-to": Wrench,
  decision: Scale,
};

/** The icon of a file: a source's, a built-in type's, a custom type's or an
 *  untyped page's. */
export function fileIcon(file: { kind: string; page_type: string }): LucideIcon {
  if (file.kind === "source") return ScrollText;
  if (file.kind !== "page") return FileText;
  if (!file.page_type) return FileQuestionMark;
  return ICONS[file.page_type] ?? FileText;
}

/** Where a type comes in Contents: the built-in types in their order, then a
 *  custom type by name, then no type (`""`). */
export function compareTypes(a: string, b: string): number {
  const rank = (type: string) => {
    const i = (BUILT_IN_TYPES as readonly string[]).indexOf(type);
    if (i >= 0) return i;
    return type ? BUILT_IN_TYPES.length : BUILT_IN_TYPES.length + 1;
  };
  return rank(a) - rank(b) || a.localeCompare(b);
}

/** Whether `type` is one of the built-in types, worded under
 *  `knowledge.types.<type>`; a custom type is shown as written. */
export function isBuiltInType(type: string): boolean {
  return (BUILT_IN_TYPES as readonly string[]).includes(type);
}
