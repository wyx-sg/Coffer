// frontend/src/components/skills/versionLabels.ts
// How a skill's History words a version (canvas 4.3.19–4.3.20): a title that
// says what was done ("Edited SKILL.md", "Added scripts/fetch_page.py",
// "Restored the version of Sep 20"), a one-line note for the chosen version,
// and the source — You, Coffer or Git, with a mark each. Sync is an
// experimental feature, so a version it wrote reads as Git, never as "Sync".
// Pure: no component, unit-tested alone.
import type { TFunction } from "i18next";
import { Bot, GitBranch, User, Vault, type LucideIcon } from "lucide-react";

import type { VaultVersionOut } from "@/lib/api/vault";
import { whenLabel } from "@/lib/knowledge/changes";

/** A version's changed file, relative to the skill's folder (`skills/<name>/`). */
export function relPath(folder: string, path: string): string {
  return path.startsWith(folder) ? path.slice(folder.length) : path;
}

export function sourceIcon(displayWriter: string): LucideIcon {
  if (displayWriter.startsWith("agent:") || displayWriter === "agent") return Bot;
  if (displayWriter === "sync") return GitBranch;
  if (displayWriter === "daemon" || displayWriter === "curation") return Vault;
  return User;
}

/** The date a version is named by: "Sep 20". */
function dayLabel(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

/** What the version did, in the words of the History list. */
export function versionTitle(
  t: TFunction,
  v: VaultVersionOut,
  folder: string,
  all: readonly VaultVersionOut[],
  locale: string,
): string {
  if (v.restored_from) {
    const from = all.find((x) => x.version === v.restored_from);
    return from
      ? t("skills.history.what.restored", { date: dayLabel(from.time, locale) })
      : t("skills.history.what.restoredHash", { version: v.restored_from.slice(0, 7) });
  }
  if (v.paths.length === 1) {
    const [only] = v.paths;
    const file = relPath(folder, only.path);
    if (only.status === "added") return t("skills.history.what.added", { file });
    if (only.status === "removed") return t("skills.history.what.removed", { file });
    return t(
      v.display_writer === "disk" ? "skills.history.what.changed" : "skills.history.what.edited",
      { file },
    );
  }
  if (v.paths.length > 1) return t("skills.history.what.files", { count: v.paths.length });
  return v.summary;
}

/** The sentence under the From / To pickers: who did it, in plain words. */
export function versionNote(
  t: TFunction,
  v: VaultVersionOut,
  folder: string,
  all: readonly VaultVersionOut[],
  isCurrent: boolean,
  locale: string,
  agentName: string,
): string {
  const file = v.paths.length === 1 ? relPath(folder, v.paths[0].path) : null;
  let note: string;
  if (v.restored_from) {
    const from = all.find((x) => x.version === v.restored_from);
    note = t("skills.history.note.restored", {
      date: from ? dayLabel(from.time, locale) : v.restored_from.slice(0, 7),
    });
  } else if (v.display_writer.startsWith("agent:")) {
    note = t("skills.history.note.agent", { agent: agentName, count: v.paths.length });
  } else if (v.display_writer === "disk") {
    note = t("skills.history.note.disk", { file: file ?? "", count: v.paths.length });
  } else if (v.display_writer === "user") {
    note = t("skills.history.note.user", { file: file ?? "", count: v.paths.length });
  } else {
    note = v.summary;
  }
  return isCurrent ? `${note} ${t("skills.history.note.current")}` : note;
}

/** "Sep 24 · Coffer": a version in a picker. */
export function versionWhen(t: TFunction, v: VaultVersionOut, locale: string): string {
  return whenLabel(t, v.time, locale);
}
