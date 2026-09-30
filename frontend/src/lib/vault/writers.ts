// frontend/src/lib/vault/writers.ts
//
// Who wrote a version of a vault file, in a word (ADR
// every-vault-write-is-a-validated-commit-naming-its-writer): you through
// Coffer, an edit found on disk, an agent (by product name), Coffer itself,
// curation, or sync. It takes the daemon's display writer (`agent:<type>` for
// an agent, else the writer), so a History tab and Settings › Data word the
// same writer the same way. Pure, unit-tested without a component.
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";

const WRITERS = new Set(["user", "disk", "agent", "daemon", "curation", "sync"]);

export function vaultWriterLabel(t: TFunction, displayWriter: string): string {
  if (displayWriter.startsWith("agent:")) {
    return agentTypeLabel(displayWriter.slice("agent:".length).replace(/-/g, "_"));
  }
  return t(`vault.writer.${WRITERS.has(displayWriter) ? displayWriter : "disk"}`);
}
