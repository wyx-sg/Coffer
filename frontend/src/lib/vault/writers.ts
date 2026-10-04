// frontend/src/lib/vault/writers.ts
//
// Who wrote a version of a vault file, in a word (ADR
// every-vault-write-is-a-validated-commit-naming-its-writer), as a skill's
// History says it (canvas 4.3.19): You (a person through Coffer, or an edit
// found on disk — also theirs), Coffer (the daemon, or a curation pass in an older version), Git (a
// sync round's merge — sync is experimental, so it is never worded "Sync"), or
// an agent by product name. It takes the daemon's display writer
// (`agent:<type>` for an agent, else the writer). Pure, unit-tested without a
// component.
import type { TFunction } from "i18next";

import { agentTypeLabel } from "@/lib/agents/display";

export function vaultWriterLabel(t: TFunction, displayWriter: string): string {
  if (displayWriter.startsWith("agent:")) {
    return agentTypeLabel(displayWriter.slice("agent:".length).replace(/-/g, "_"));
  }
  if (displayWriter === "daemon" || displayWriter === "curation") return t("vault.writer.daemon");
  if (displayWriter === "sync") return t("vault.writer.sync");
  // A person's own edit — through Coffer, on disk, or a writer this build does
  // not know — reads as what it most likely is.
  return t("vault.writer.user");
}
