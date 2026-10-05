// frontend/src/components/history/VaultHistoryView.tsx
//
// A History tab (spec web-ui "Show a vault file's history on a History tab"):
// the versions of one vault file — a knowledge document — or folder — a
// skill's master folder — read from the vault's git history, in the one split
// every history shares (VersionHistorySplit). On the left the versions newest
// first, each with what it did, who wrote it (the commit's writer: you, an edit
// on disk, an agent, Coffer, sync) and when, and the lines it moved; the
// newest wears Current and is chosen when the tab opens. On the right the
// chosen version's diff and Restore this version… (VaultVersionPanel). A
// history that cannot be read is one Load error row with Retry; the rest of
// the page keeps working.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, GitBranch, History, User, Vault, type LucideIcon } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { LoadErrorRow } from "@/components/LoadErrorRow";
import { VaultVersionPanel } from "@/components/history/VaultVersionPanel";
import { VersionHistorySplit } from "@/components/history/VersionHistorySplit";
import { Skeleton } from "@/components/ui/skeleton";
import { useVaultHistory } from "@/lib/hooks/useVaultHistory";
import { whenLabel } from "@/lib/knowledge/changes";
import { vaultWriterLabel, versionCounts, versionTitle } from "@/lib/vault/versionLabels";

interface Props {
  /** The vault-relative path: a file, or a folder ending in `/`. */
  path: string;
  /** Names the remembered divider position. */
  storageKey: string;
  /** How the split reaches the window's bottom (VersionHistorySplit). */
  fill?: "window" | "parent";
}

function writerIcon(displayWriter: string): LucideIcon {
  if (displayWriter.startsWith("agent")) return Bot;
  if (displayWriter === "sync") return GitBranch;
  if (displayWriter === "daemon" || displayWriter === "curation") return Vault;
  return User;
}

export function VaultHistoryView({ path, storageKey, fill }: Props) {
  const { t, i18n } = useTranslation();
  const history = useVaultHistory(path);
  const [chosen, setChosen] = useState<string | null>(null);

  if (history.isPending) {
    return (
      <div className="space-y-2" aria-busy>
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-3/5" />
      </div>
    );
  }
  if (history.error) {
    return (
      <LoadErrorRow
        title={t("history.failedTitle")}
        error={history.error}
        onRetry={() => void history.refetch()}
      />
    );
  }

  const versions = history.data.versions;
  if (versions.length === 0) {
    return (
      <EmptyState icon={History} title={t("history.emptyTitle")} description={t("history.empty")} />
    );
  }
  const index = Math.max(
    0,
    versions.findIndex((v) => v.version === chosen),
  );

  return (
    <VersionHistorySplit
      storageKey={storageKey}
      fill={fill}
      versions={versions}
      getKey={(v) => v.version}
      selectedIndex={index}
      onSelect={(i) => setChosen(versions[i].version)}
      listLabel={t("history.listLabel")}
      currentLabel={t("history.current")}
      dividerLabel={t("splitView.resizeList")}
      renderRow={(v) => {
        const Icon = writerIcon(v.display_writer);
        const { added, removed } = versionCounts(v);
        return {
          icon: (
            <span className="inline-flex size-[26px] shrink-0 items-center justify-center rounded-full bg-chip text-text-muted">
              <Icon className="size-3.5" aria-hidden />
            </span>
          ),
          title: versionTitle(t, v, path, versions, i18n.language),
          subline: `${vaultWriterLabel(t, v.display_writer)} · ${whenLabel(t, v.time, i18n.language)}`,
          trailing: added || removed ? `+${added} −${removed}` : undefined,
        };
      }}
      detail={
        <VaultVersionPanel
          key={versions[index].version}
          path={path}
          versions={versions}
          index={index}
        />
      }
    />
  );
}
