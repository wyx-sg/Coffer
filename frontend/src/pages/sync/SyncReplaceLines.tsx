// frontend/src/pages/sync/SyncReplaceLines.tsx — the lines of a "replace" join preview.
//
// The remote holds an older layout of the vault; this Mac's vault is the
// source of truth and replaces it (spec vault-sync "Refuse a newer-layout remote
// and replace an older one"). Stated before the button: what goes up, which files only
// the old remote had go away, that git history keeps them, and that machines
// still on the older layout must upgrade.
import { useTranslation } from "react-i18next";

import type { JoinPreview } from "@/lib/api/sync";
import { areaSummary } from "./syncJoinAreas";
import { JoinLine } from "./SyncJoinLine";

export function SyncReplaceLines({ preview }: { preview: JoinPreview }) {
  const { t } = useTranslation();
  const hidden = Math.max(0, preview.deleted_total - preview.deleted.length);
  return (
    <ul className="flex flex-col" data-testid="sync-join-preview">
      <JoinLine
        mark="↑"
        testId="sync-join-pushed"
        title={t("sync.join.pushed", { count: preview.pushed_files })}
        body={preview.pushed_files > 0 ? areaSummary(t, preview.pushed) : undefined}
      />
      {preview.deleted_total > 0 ? (
        <JoinLine
          mark="−"
          tone="warn"
          testId="sync-join-deleted"
          title={t("sync.join.replaceGone", { count: preview.deleted_total })}
          body={
            preview.deleted.join(", ") +
            (hidden > 0 ? ` ${t("sync.join.replaceGoneMore", { count: hidden })}` : "")
          }
        />
      ) : null}
      <JoinLine
        mark="="
        testId="sync-join-kept"
        title={t("sync.join.replaceKept")}
        body={t("sync.join.replaceKeptBody")}
      />
      <JoinLine
        mark="!"
        tone="warn"
        testId="sync-join-others"
        title={t("sync.join.replaceOthers")}
        body={t("sync.join.replaceOthersBody")}
      />
    </ul>
  );
}
