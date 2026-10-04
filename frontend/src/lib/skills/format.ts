// frontend/src/lib/skills/format.ts
// The short forms the Skills page prints: a day ("Sep 24"), a day with its
// time ("Sep 26 at 16:40", "today at 09:02") and a folder inside a repository. The canvas reads dates this way on the skill header, the
// Delivery rows and the drift findings; the full timestamp stays one hover
// away wherever it matters (formatDateTime).

function valid(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** "Sep 24" (the year only when it is not this one). */
export function shortDay(iso: string, locale: string, now: Date = new Date()): string {
  const d = valid(iso);
  if (!d) return iso;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  }).format(d);
}

/** "16:40". */
export function clockTime(iso: string, locale: string): string {
  const d = valid(iso);
  if (!d) return iso;
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

/** Whether `iso` falls on today, for the "today at 09:02" phrasing. */
export function isToday(iso: string, now: Date = new Date()): boolean {
  const d = valid(iso);
  return d !== null && sameDay(d, now);
}

/** A folder inside a repository as the canvas writes it ("terraform-plan/"),
 *  or null at the top of the repository. */
export function folderLabel(subpath: string): string | null {
  const s = subpath.replace(/^\.?\/*/, "").replace(/\/+$/, "");
  return s ? `${s}/` : null;
}
