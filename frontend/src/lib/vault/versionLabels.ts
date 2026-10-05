// frontend/src/lib/vault/versionLabels.ts
//
// How a History tab words a version of a vault file or folder (spec web-ui
// "Show a vault file's history on a History tab"): who wrote it in a word —
// you, an edit on disk, an agent by product name, Coffer, or sync (the
// commit's `Coffer-Writer`, as the daemon's display writer `agent:<type>` for
// an agent; ADR every-vault-write-is-a-validated-commit-naming-its-writer) —
// and a title that says what was done ("Edited", "Added scripts/fetch.py",
// "Restored the version of 20 Sep"). Pure: no component, unit-tested alone.
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";
import type { VaultVersionOut } from "@/lib/api/vault";

/** Who wrote a version, in a word. */
export function vaultWriterLabel(t: TFunction, displayWriter: string): string {
  if (displayWriter.startsWith("agent:")) {
    return agentTypeLabel(displayWriter.slice("agent:".length).replace(/-/g, "_"));
  }
  switch (displayWriter) {
    case "agent":
      return t("history.writer.agent");
    case "daemon":
    case "curation":
      return t("history.writer.daemon");
    case "sync":
      return t("history.writer.sync");
    case "disk":
      return t("history.writer.disk");
    default:
      // A person through Coffer, or a writer this build does not know.
      return t("history.writer.user");
  }
}

/** A path inside the history's folder (`skills/pdf/` → `scripts/x.py`). */
export function relPath(base: string, path: string): string {
  return base.endsWith("/") && path.startsWith(base) ? path.slice(base.length) : path;
}

/** The date a version is named by: "20 Sep". */
function dayLabel(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

/** What the version did, in the words of the version list. `base` is the
 *  history's path: a file, or a folder ending in `/`. */
export function versionTitle(
  t: TFunction,
  v: VaultVersionOut,
  base: string,
  all: readonly VaultVersionOut[],
  locale: string,
): string {
  if (v.restored_from) {
    const from = all.find((x) => x.version === v.restored_from);
    return from
      ? t("history.what.restored", { date: dayLabel(from.time, locale) })
      : t("history.what.restoredHash", { version: v.restored_from.slice(0, 7) });
  }
  if (v.paths.length === 1) {
    const [only] = v.paths;
    if (!base.endsWith("/")) {
      if (only.status === "added") return t("history.what.created");
      if (only.status === "removed") return t("history.what.deleted");
      return t("history.what.edited");
    }
    const file = relPath(base, only.path);
    if (only.status === "added") return t("history.what.added", { file });
    if (only.status === "removed") return t("history.what.removed", { file });
    return t("history.what.changed", { file });
  }
  if (v.paths.length > 1) return t("history.what.files", { count: v.paths.length });
  return v.summary;
}

/** The lines a version moved, summed over its files. */
export function versionCounts(v: VaultVersionOut): { added: number; removed: number } {
  return v.paths.reduce(
    (sum, p) => ({ added: sum.added + p.added, removed: sum.removed + p.removed }),
    { added: 0, removed: 0 },
  );
}
