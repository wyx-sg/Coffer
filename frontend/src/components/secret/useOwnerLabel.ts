// src/components/secret/useOwnerLabel.ts — a secret's owner in words ("MCP server · jira"), and its kind alone.
import { useTranslation } from "react-i18next";

import type { OwnerKind } from "@/lib/secrets/listState";
import type { Owner } from "./secretOwners";

/** The kind of owner as the user knows it, and the owner line under a secret's name. */
export function useOwnerLabel() {
  const { t } = useTranslation();
  const kindLabel = (kind: OwnerKind) => t(`secrets.owner.${kind}`);
  /** `fallback` (the raw ref) stands in when the owner has no name of its own. */
  const ownerLine = (owner: Owner, fallback: string, standalone: boolean) => {
    if (owner.name) {
      const more = owner.more > 0 ? ` +${owner.more}` : "";
      return `${kindLabel(owner.kind)} · ${owner.name}${more}`;
    }
    if (owner.kind === "sync") return `${kindLabel("sync")} · ${t("secrets.owner.syncToken")}`;
    if (standalone) return t("secrets.owner.standalone");
    return owner.kind === "other" ? fallback : `${kindLabel(owner.kind)} · ${fallback}`;
  };
  return { kindLabel, ownerLine };
}
